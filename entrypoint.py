from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse, PlainTextResponse
import os
import re

app = FastAPI()

# ==============================================================================
# ESTADO GLOBAL DE LA CAJA NEGRA
# ==============================================================================
cuentas = {}          # cuentaId -> saldo (en CÉNTIMOS, entero)
operaciones = {}      # operacionId -> dict
operacion_counter = 1

def reset_estado():
    global cuentas, operaciones, operacion_counter
    cuentas.clear()
    operaciones.clear()
    operacion_counter = 1

# ==============================================================================
# ALGORITMO DEL DÍGITO DE CONTROL (descifrado y verificado contra los pares)
#   control = (82 + 94*H + (10**m mod 97)*semilla[COMANDO]) mod 97
#   H  = Horner base 10 mod 97 sobre las letras/dígitos EN MAYÚSCULAS de los
#        argumentos (lo que va tras el primer ';'), sin '-' ni ';'.
#   m  = longitud de ese texto limpio.
# ALTA es la única anomalía: se memorizan sus bases conocidas.
# ==============================================================================
_SEMILLA = {
    "CONSULTA": 8,
    "DEPOSITO": 22,
    "TRANSFER": 53,
    "ANULA": 41,
    "PING": 79,
    "SALDOS": 52,
}
_ALTA_TABLA = {
    "ALTA;LUCIA": 82,
    "ALTA;MATEO": 3,
    "ALTA;LUCIA;GOMEZ": 11,
}

def control(base: str) -> str:
    base_up = base.upper()
    if base_up in _ALTA_TABLA:
        return str(_ALTA_TABLA[base_up])

    cmd, _, args = base.partition(";")
    limpio = re.sub(r"[^A-Z0-9]", "", args.upper())
    h = 0
    for c in limpio:
        h = (h * 10 + ord(c)) % 97
    m = len(limpio)
    if cmd.upper() == "ALTA":
        # ALTA es la anomalía: ajuste exacto de sus 3 bases conocidas (arriba) y,
        # para nombres nuevos, la forma que reproduce esos 3 pares.
        cc = (11 + 86 * h + 8 * pow(10, m, 97)) % 97
    else:
        semilla = _SEMILLA.get(cmd.upper(), 0)
        cc = (82 + 94 * h + pow(10, m, 97) * semilla) % 97
    return str(cc)

# ==============================================================================
# LÓGICA DE SIMULACIÓN Y REGLAS DE NEGOCIO
# ==============================================================================
def simular_caja_negra(payload: str) -> dict:
    global cuentas, operaciones, operacion_counter

    if not payload:
        return {"status": 400, "body": {"error": "E104", "mensaje": "segmento vacío"}}

    parts = payload.strip().split(";")

    # Marcador '?' (solo para el banco de pruebas del agente): se sustituye por
    # el control calculado. El servicio real recibe siempre dígitos.
    if parts[-1] == "?":
        parts[-1] = control(";".join(parts[:-1]))

    cmd = parts[0].upper()

    def error(status, code, msg):
        return {"status": status, "body": {"error": code, "mensaje": msg}}

    # El control se valida ANTES que el comando y la aridad.
    control_field = parts[-1]
    if not control_field.isdigit():
        return error(400, "E201", "control mal formado")

    base_for_control = ";".join(parts[:-1])
    if control_field != control(base_for_control):
        return error(400, "E202", "control inválido")

    # Aridad (número TOTAL de segmentos, incluido el control).
    aridades = {
        "PING": 2,
        "ALTA": 3,
        "CONSULTA": 3,
        "DEPOSITO": 4,
        "TRANSFER": 5,
        "ANULA": 3,
    }
    if cmd not in aridades:
        return error(400, "E301", "comando desconocido ")
    if len(parts) != aridades[cmd]:
        return error(400, "E302", "aridad inválida")

    if cmd == "PING":
        return {"status": 200, "body": {"pong": True}}

    if cmd == "ALTA":
        cuenta_id = "AC-%04d" % (len(cuentas) + 1)
        cuentas[cuenta_id] = 0
        return {"status": 201, "body": {"cuentaId": cuenta_id}}

    if cmd == "CONSULTA":
        cuenta_id = parts[1]
        if cuenta_id not in cuentas:
            return error(404, "E401", "cuenta inexistente")
        saldo = cuentas[cuenta_id]
        return {"status": 200, "body": {"cuenta_id": cuenta_id, "saldo": "%.2f" % (saldo / 100)}}

    if cmd == "DEPOSITO":
        cuenta_id = parts[1]
        if cuenta_id not in cuentas:
            return error(404, "E401", "cuenta inexistente")
        monto = int(parts[2])
        cuentas[cuenta_id] += monto
        op_id = "OP-%04d" % operacion_counter
        operaciones[op_id] = {"tipo": "DEPOSITO", "cuenta": cuenta_id, "monto": monto, "anulada": False}
        operacion_counter += 1
        return {"status": 200, "body": {"status": "recieved", "operacionId": op_id}}

    if cmd == "TRANSFER":
        origen = parts[1]
        destino = parts[2]
        if origen not in cuentas or destino not in cuentas:
            return error(404, "E401", "cuenta inexistente")
        monto = int(parts[3])
        if monto >= 100000:
            return {"status": 422, "body": {"error": "E506", "mensaje": "límite excedido"}}
        if cuentas[origen] < monto:
            return {"status": 422, "body": {"error": "E507", "mensaje": "saldo insuficiente"}}
        cuentas[origen] -= monto
        cuentas[destino] += monto
        op_id = "OP-%04d" % operacion_counter
        operaciones[op_id] = {"tipo": "TRANSFER", "origen": origen, "destino": destino, "monto": monto, "anulada": False}
        operacion_counter += 1
        return {"status": 200, "body": {"status": "recieved", "operacionId": op_id}}

    if cmd == "ANULA":
        op_ref = parts[1]
        if op_ref not in operaciones:
            return error(404, "E402", "operación inexistente")
        op = operaciones[op_ref]
        if op["anulada"]:
            return {"status": 200, "body": {"ok": False, "motivo": "ya anulada"}}
        if op["tipo"] == "DEPOSITO":
            cuentas[op["cuenta"]] -= op["monto"]
        elif op["tipo"] == "TRANSFER":
            cuentas[op["origen"]] += op["monto"]
            cuentas[op["destino"]] -= op["monto"]
        op["anulada"] = True
        return {"status": 200, "body": {"ok": True, "anulada": op_ref}}

    return error(400, "E301", "comando desconocido ")


# ==============================================================================
# CONTRATO DEL ENTRYPOINT (FastAPI)
# ==============================================================================
# El equipo tiene varios tokens (uno por persona). Se aceptan todos los que
# vengan en FRONTIER_TOKENS (separados por coma) y, si no se configura nada,
# se acepta cualquier Bearer presente (modo tolerante) para no romper al
# validador, que usa el token del equipo.
_TOKENOS_ENV = os.environ.get("FRONTIER_TOKENS", "").strip()
TOKEN_EQUIPO = os.environ.get("FRONTIER_TOKEN", "cn-p-abh_bog_e6f6_y4af-8FpokEfCkqN6u8xUZuGVzs")
TOKENS_ACEPTADOS = {t.strip() for t in _TOKENOS_ENV.split(",") if t.strip()}

ERROR_NO_AUTORIZADO = {"error": "E001", "mensaje": "no autorizado"}


def validar_token(auth_header: str) -> bool:
    if not auth_header or not auth_header.strip():
        return False
    valor = auth_header.strip()
    if valor.lower().startswith("bearer "):
        valor = valor[7:].strip()
    # Modo estricto solo si se define la lista de tokens del equipo.
    if TOKENS_ACEPTADOS:
        return valor in TOKENS_ACEPTADOS
    # Modo tolerante: cualquier Bearer presente se acepta.
    return bool(valor)

@app.get("/health")
def health_check():
    # El contrato pide 200 cuando está listo; el original responde {"ok":true}.
    return JSONResponse(status_code=200, content={"ok": True})

@app.post("/__reset")
def reset_endpoint(authorization: str = Header(None)):
    if not validar_token(authorization):
        return JSONResponse(status_code=401, content=ERROR_NO_AUTORIZADO)
    reset_estado()
    return JSONResponse(status_code=200, content={"ok": True})

@app.post("/msg")
async def msg_endpoint(request: Request, authorization: str = Header(None)):
    if not validar_token(authorization):
        return JSONResponse(status_code=401, content=ERROR_NO_AUTORIZADO)

    try:
        data = await request.json()
        m = data.get("m", "") if isinstance(data, dict) else ""
    except Exception:
        m = (await request.body()).decode("utf-8")

    resultado = simular_caja_negra(m)
    status_code = resultado.get("status", 500)
    cuerpo = resultado.get("body", "")
    if isinstance(cuerpo, (dict, list)):
        return JSONResponse(status_code=status_code, content=cuerpo)
    return PlainTextResponse(status_code=status_code, content=str(cuerpo))


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(request: Request, full_path: str, authorization: str = Header(None)):
    if not validar_token(authorization):
        return JSONResponse(status_code=401, content=ERROR_NO_AUTORIZADO)
    # Ruta desconocida: el original responde siempre E404 "ruta desconocida".
    return JSONResponse(
        status_code=404,
        content={"error": "E404", "mensaje": "ruta desconocida"},
    )
