# Estado global del sistema
_cuentas = {}         # clave: cuentaId, valor: {"nombre": str, "saldo": int}
_next_cuenta = 1      # para generar IDs: AC-0001, AC-0002, ...
_next_operacion = 1   # para generar operacionId: OP-0001,...
_operaciones = {}     # clave: operacionId, valor: dict (tipo, monto, anulada)
_estado_reset = True  # indica que se ha hecho reset

def _reset():
    global _cuentas, _next_cuenta, _next_operacion, _operaciones
    _cuentas = {}
    _next_cuenta = 1
    _next_operacion = 1
    _operaciones = {}

def _get_cuenta_id():
    global _next_cuenta
    cid = f"AC-{_next_cuenta:04d}"
    _next_cuenta += 1
    return cid

def _get_operacion_id():
    global _next_operacion
    oid = f"OP-{_next_operacion:04d}"
    _next_operacion += 1
    return oid

def simular_caja_negra(payload):
    global _cuentas, _operaciones
    # Si payload es __RESET__, reinicia el estado
    if payload.strip() == "__RESET__":
        _reset()
        return {"status": 200, "body": "OK"}
    
    # Separar campos por ';'
    partes = payload.strip().split(';')
    if len(partes) == 0:
        return {"status": 400, "body": "Formato Inválido"}
    
    # El control es el último campo; si es '?' se reemplaza usando control() sobre la base
    if partes[-1] == "?":
        base = ";".join(partes[:-1]).upper()
        partes[-1] = control(base)
    # Verificar si el campo de control es numérico, de lo contrario error de FORMATO
    ctrl_field = partes[-1]
    if not ctrl_field.isdigit():
        return {"status": 400, "body": {"error": "E201", "mensaje": "control mal formado"}}
    
    # Reconstruir la base (todo en mayúsculas, sin el control)
    base = ";".join(partes[:-1]).upper()
    esperado = control(base)
    if ctrl_field != esperado:
        return {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}
    
    # Extraer comando (case-insensitive)
    comando = partes[0].upper()
    args = partes[1:-1]
    
    # Procesamiento según comando y validación de aridad:
    if comando == "PING":
        if len(args) != 0:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        return {"status": 200, "body": {"pong": True}}
    
    elif comando == "ALTA":
        # ALTA debe tener 1 o 2 argumentos: nombre, opcional apellido -> aridad exacta: 1 o 2
        if len(args) not in [1, 2]:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Se ignora si se envía comando con el nombre repetido, se crea nueva cuenta siempre
        cuentaId = _get_cuenta_id()
        _cuentas[cuentaId] = {"nombre": " ".join(args), "saldo": 0}
        return {"status": 201, "body": {"cuentaId": cuentaId}}
    
    elif comando == "CONSULTA":
        # CONSULTA;cuenta
        if len(args) != 1:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        cuenta = args[0].upper()
        # Buscar cuenta por id
        if cuenta not in _cuentas:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        # Devuelve saldo format con dos decimales (divide saldo interno, suponemos en centavos)
        saldo = _cuentas[cuenta]["saldo"]
        # Para algunos casos se observó cambio de formato, se devuelve string con formato "0.00"
        return {"status": 200, "body": {"cuenta_id": cuenta, "saldo": f"{saldo/100:.2f}"}}
    
    elif comando == "DEPOSITO":
        # DEPOSITO;cuenta;monto
        if len(args) != 2:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        cuenta = args[0].upper()
        if cuenta not in _cuentas:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        try:
            monto = int(args[1])
        except:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Deposito aumenta saldo
        _cuentas[cuenta]["saldo"] += monto
        opid = _get_operacion_id()
        _operaciones[opid] = {"tipo": "DEPOSITO", "monto": monto, "anulada": False}
        return {"status": 200, "body": {"status": "recieved", "operacionId": opid}}
    
    elif comando == "TRANSFER":
        # TRANSFER;cuentaDesde;cuentaHacia;monto
        if len(args) != 3:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        origen = args[0].upper()
        destino = args[1].upper()
        if origen not in _cuentas or destino not in _cuentas:
            return {"status": 404, "body": {"error": "E401", "mensaje": "cuenta inexistente"}}
        try:
            monto = int(args[2])
        except:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        # Límite de transferencia: supongamos limite 100000
        if monto > 100000:
            return {"status": 422, "body": {"error": "E506", "mensaje": "límite excedido"}}
        # Verificar saldo
        if _cuentas[origen]["saldo"] < monto:
            return {"status": 422, "body": {"error": "E507", "mensaje": "saldo insuficiente"}}
        # Realizar transferencia
        _cuentas[origen]["saldo"] -= monto
        _cuentas[destino]["saldo"] += monto
        opid = _get_operacion_id()
        _operaciones[opid] = {"tipo": "TRANSFER", "monto": monto, "anulada": False}
        return {"status": 200, "body": {"status": "recieved", "operacionId": opid}}
    
    elif comando == "ANULA":
        # ANULA;operacionId
        if len(args) != 1:
            return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
        opid = args[0].upper()
        if opid not in _operaciones:
            return {"status": 404, "body": {"error": "E402", "mensaje": "operación inexistente"}}
        # Si ya anulada, devolver mensaje distinto (según evidencia)
        if _operaciones[opid]["anulada"]:
            return {"status": 404, "body": {"error": "E402", "mensaje": "operación inexistente"}}
        _operaciones[opid]["anulada"] = True
        return {"status": 200, "body": {"ok": True, "anulada": opid}}
    
    elif comando == "SALDOS":
        # Comando desconocido según evidencia
        return {"status": 400, "body": {"error": "E301", "mensaje": "comando desconocido "}}
    
    else:
        # Comando no reconocido
        return {"status": 400, "body": {"error": "E301", "mensaje": "comando desconocido "}}