# Simulador de la caja negra
# El estado se mantiene a nivel módulo
_estado = {
    "cuentas": {},  # mapa de cuentaId -> {"nombre": <str>, "saldo": <int>}
    "operaciones": {},  # mapa de operacionId -> {"operacion": str, "estado": "recieved" o anulado, ...}
    "contador": 1
}

def simular_caja_negra(payload):
    global _estado
    # Reset especial si se recibe '__RESET__'
    if payload.strip() == "__RESET__":
        _estado = {"cuentas": {}, "operaciones": {}, "contador": 1}
        return {"status": 200, "body": "reset exitoso"}
    
    # Se asume payload en formato "COMANDO;arg1;arg2;...;control"
    campos = payload.split(";")
    # Extraer campo de control (si se proporciona) siempre es el último,
    # pero si termina en "?" se computa usando la función control()
    if campos[-1] == "?":
        base = ";".join(campos[:-1])
        ctrl = control(base.upper())
        campos[-1] = ctrl
        payload = ";".join(campos)
    # Separar el control y la base
    base = ";".join(campos[:-1]).upper()
    ctrl_enviado = campos[-1]
    ctrl_calculado = control(base)
    # Validación de formato: El control debe ser dígitos únicamente
    if not ctrl_enviado.isdigit():
        return {"status": 400, "body": {"error": "E201", "mensaje": "control mal formado"}}
    if ctrl_enviado != ctrl_calculado:
        return {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}
    
    # Procesar comando (comando es case-insensitive)
    comando = campos[0].upper()
    args = [arg for arg in campos[1:-1]]
    # Aridad (cantidad de argumentos) válida segun catálogo (ejemplo simplificado)
    if comando == "ALTA":
        # Se esperan 1 o 2 argumentos: nombre y opcional apellido
        if len(args) < 1 or len(args) > 2:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Crear cuenta; se usa un ID ficticio
        nombre = args[0].upper()
        cuenta_id = "AC-%04d" % (len(_estado["cuentas"]) + 1)
        _estado["cuentas"][cuenta_id] = {"nombre": nombre, "saldo": 0}
        return {"status": 201, "body": {"cuentaId": cuenta_id}}
    elif comando == "DEPOSITO":
        # Se esperan 2 argumentos: cuentaId y monto (en enteros)
        if len(args) != 2:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        cuenta_id = args[0].upper()
        if cuenta_id not in _estado["cuentas"]:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        try:
            monto = int(args[1])
        except:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Actualiza saldo
        _estado["cuentas"][cuenta_id]["saldo"] += monto
        operacion_id = "OP-%04d" % (_estado["contador"])
        _estado["contador"] += 1
        _estado["operaciones"][operacion_id] = {"operacion": payload, "estado": "recieved"}
        return {"status": 200, "body": {"status": "recieved", "operacionId": operacion_id}}
    elif comando == "TRANSFER":
        # Se esperan 3 argumentos: cuentaOrigen, cuentaDestino y monto
        if len(args) != 3:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        origen = args[0].upper()
        destino = args[1].upper()
        if origen not in _estado["cuentas"]:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        if destino not in _estado["cuentas"]:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        try:
            monto = int(args[2])
        except:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Límite de transferencia arbitrario (por ejemplo, 100000)
        if monto > 100000:
            return {"status": 422, "body": {"error": "E506", "mensaje": "límite excedido"}}
        # Validar saldo
        if _estado["cuentas"][origen]["saldo"] < monto:
            return {"status": 422, "body": {"error": "E507", "mensaje": "saldo insuficiente"}}
        _estado["cuentas"][origen]["saldo"] -= monto
        _estado["cuentas"][destino]["saldo"] += monto
        operacion_id = "OP-%04d" % (_estado["contador"])
        _estado["contador"] += 1
        _estado["operaciones"][operacion_id] = {"operacion": payload, "estado": "recieved"}
        return {"status": 200, "body": {"status": "recieved", "operacionId": operacion_id}}
    elif comando == "CONSULTA":
        # Se espera 1 argumento: cuentaId
        if len(args) != 1:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        cuenta_id = args[0].upper()
        if cuenta_id not in _estado["cuentas"]:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        saldo = _estado["cuentas"][cuenta_id]["saldo"]
        # Para compatibilidad, saldo formateado a dos decimales
        return {"status": 200, "body": {"cuenta_id": cuenta_id, "saldo": "{:.2f}".format(saldo)}}
    elif comando == "PING":
        return {"status": 200, "body": {"pong": True}}
    elif comando == "SALDOS":
        # Se espera 1 argumento: cuentaId (aunque catalogado como comando desconocido en la evidencia)
        return {"status": 400, "body": {"error": "E301", "mensaje": "comando desconocido "}}
    elif comando == "ANULA" or comando == "ANULA":
        # Se espera 1 argumento: operacionId
        if len(args) != 1:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        operacion_id = args[0].upper()
        if operacion_id not in _estado["operaciones"]:
            return {"status": 404, "body": {"error": "E402", "mensaje": "operación inexistente"}}
        # Para simplificar, si ya fue anulada respondemos 404
        if _estado["operaciones"][operacion_id].get("anulada", False):
            return {"status": 404, "body": {"error": "E402", "mensaje": "operación inexistente"}}
        _estado["operaciones"][operacion_id]["anulada"] = True
        return {"status": 200, "body": {"ok": True, "anulada": operacion_id}}
    else:
        return {"status": 400, "body": {"error": "E301", "mensaje": "comando desconocido "}}