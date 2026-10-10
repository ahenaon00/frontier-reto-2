"""Pruebas lógicas de las mejoras del agente (sin tocar la red ni OpenRouter):

- Pistas aritméticas: detecta el módulo 97 por el wrap y NO afirma módulo si no
  hay envoltura.
- Pares (base -> control) normalizados a mayúsculas y con rechazo por E201/E202.
- Agrupación de payloads por resultado.
- La réplica devuelve desglose por grupo de resultado.
- El ejecutor bloquea controles no numéricos (placeholders) sin gastar request.

Ejecutar:  python3 pruebas/test_agente_logica.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agente_matematico as ag

tmp = tempfile.mkdtemp()
ag.PATRONES_JSONL = os.path.join(tmp, "patrones.jsonl")
ag.EJEMPLOS_NUEVOS = os.path.join(tmp, "ejemplos_nuevos.jsonl")
ag.REPETIR = False

# --- 1) Pistas aritméticas: CONSULTA;AC-000n → 14,11,8,5 y AC-0009 → 87 ---
pares = {
    "CONSULTA;AC-0001": ["14"],
    "CONSULTA;AC-0002": ["11"],
    "CONSULTA;AC-0003": ["8"],
    "CONSULTA;AC-0004": ["5"],
    "CONSULTA;AC-0009": ["87"],
    "PING": ["64"],
}
pistas = ag.extraer_pistas_aritmeticas(pares)
texto_pistas = "\n".join(pistas)
assert "módulo 97" in texto_pistas, texto_pistas
print("OK pistas: detecta el módulo 97:", texto_pistas)

# Sin AC-0009 (no hay wrap) NO se debe afirmar ningún módulo.
pares_sin_wrap = {
    "CONSULTA;AC-0001": ["14"], "CONSULTA;AC-0002": ["11"],
    "CONSULTA;AC-0003": ["8"], "CONSULTA;AC-0004": ["5"],
}
pistas2 = ag.extraer_pistas_aritmeticas(pares_sin_wrap)
t2 = "\n".join(pistas2)
assert "sin envoltura" in t2 and "módulo aún no está determinado" in t2, pistas2
print("OK pistas sin wrap (no afirma módulo):", pistas2[0])

# --- 2) Normalización a mayúsculas: PING;64 y ping;64 colapsan ---
pasos = [
    {"payload": "PING;64", "observado": {"status": 200, "body": {"pong": True}}},
    {"payload": "ping;64", "observado": {"status": 200, "body": {"pong": True}}},
    {"payload": "PING;65", "observado": {"status": 400, "body": {"error": "E202"}}},
    {"payload": "Ping;63", "observado": {"status": 400, "body": {"error": "E202"}}},
]
ctr = ag.extraer_controles(pasos)
assert ctr == {"PING": ["64"]}, ctr
print("OK pares normalizados a mayúsculas:", ctr)

# --- 3) Grupos por resultado ---
grupos = ag.agrupar_por_resultado(pasos)
claves = [k for k, _ in grupos]
assert "200" in claves and "400 control_rechazado" in claves, grupos
print("OK grupos por resultado:", grupos)

# --- 4) probar_replica devuelve 4 valores con desglose por grupo ---
codigo = '''
def simular_caja_negra(payload):
    if payload.strip().upper() == "PING;64":
        return {"status": 200, "body": {"pong": True}}
    if payload.strip().upper().startswith("PING"):
        return {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}
    return {"status": 400, "body": {"error": "E302", "mensaje": "aridad inválida"}}
'''
sesiones = {
    "replay": [
        {"payload": "PING;64", "observado": {"status": 200, "body": {"pong": True}}},
        {"payload": "PING;65", "observado": {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}},
        {"payload": "PING;63", "observado": {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}},
    ]
}
score, fallos, desglose, dg = ag.probar_replica(codigo, sesiones)
assert score == 1.0, (score, fallos)
assert dg.get("200") == [1, 1] and dg.get("400 control_rechazado") == [2, 2], dg
print("OK réplica por grupo:", dg)

# --- 5) Bloqueo de control no numérico (placeholder) sin gastar request ---
class FakeCliente:
    def __init__(self):
        self.n = 0
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1

    def msg(self, payload, seq="", hipotesis=""):
        self.n += 1
        return {"status": 200, "response": {}}


cliente = FakeCliente()
alm = ag.Almacen()
exp = [
    {"payload": "ALTA;Sofia;__CTRL__", "prediccion": None, "motivo": "placeholder"},
    {"payload": "ALTA;Nuevo;44", "prediccion": None, "motivo": "válido"},
]
res, omitidos = ag.ejecutar_experimentos(cliente, alm, exp, "ronda_t", ag.Presupuesto(100))
alm.cerrar()
assert [r["payload"] for r in res] == ["ALTA;Nuevo;44"], res
assert omitidos == 1, omitidos
assert cliente.n == 1, cliente.n  # solo se envió 1 al servicio
print("OK bloqueo de placeholder sin gastar request (se envió 1).")

# --- 6b) El marcador '?' se sustituye con la candidata `control(base)` ---
cliente2 = FakeCliente()
alm2 = ag.Almacen()
control_fn = ag._compilar_funcion("def control(base):\n    return str(len(base) % 97)\n", "control")
assert control_fn is not None
exp2 = [
    {"payload": "ALTA;Sofia;?", "prediccion": None, "motivo": "gen"},
    {"payload": "ALTA;Pedro;__CTRL__", "prediccion": None, "motivo": "gen2"},
]
res2, omit2 = ag.ejecutar_experimentos(cliente2, alm2, exp2, "ronda_q",
                                       ag.Presupuesto(100), control_fn=control_fn)
alm2.cerrar()
# 'ALTA;Sofia;?' -> base 'ALTA;SOFIA' (len 10) -> control '10'
# '__CTRL__' también es marcador -> base 'ALTA;PEDRO' (len 10) -> control '10'
assert [r["payload"] for r in res2] == ["ALTA;Sofia;10", "ALTA;Pedro;10"], res2
assert all(r["auto"] is True for r in res2), res2
assert omit2 == 0, omit2
assert cliente2.n == 2, cliente2.n
print("OK sustitución de marcadores ('?', '__CTRL__') con control(base) (auto=true).")

# --- 6c) El feedback reporta el resultado del control automático ('?') ---
fb = ag.formatear_feedback(
    [], 0.5, [],
    control_info={"aciertos": 15, "total": 15, "fallos": []},
    auto_info={"total": 3, "fallos": 2,
               "bases_fallidas": ["ALTA;Nueva;10", "ALTA;Otra;7"]})
assert "GENERALIZA" in fb, fb
assert "marcador '?'" in fb and "NO generaliza" in fb, fb
assert "ALTA;Nueva;10" in fb, fb
print("OK feedback del control automático ('?' generaliza o no).")

# --- 6d) La réplica recibe `control` inyectado (antes daba NameError) ---
rep = '''
def simular_caja_negra(payload):
    if payload == "__RESET__":
        return {"status": 200, "body": "ok"}
    partes = payload.split(";")
    base = ";".join(partes[:-1]).upper()
    if partes[-1] != control(base):
        return {"status": 400, "body": {"error": "E202", "mensaje": "control inválido"}}
    return {"status": 200, "body": {"pong": True}}
'''
ctrl = 'def control(base):\n    return {"PING": "64"}.get(base.upper(), "0")\n'
ses = {"replay": [
    {"payload": "PING;64", "observado": {"status": 200, "body": {"pong": True}}},
]}
s_wo, _, _, _ = ag.probar_replica(rep, ses)
s_wi, _, _, _ = ag.probar_replica(rep, ses, control_codigo=ctrl)
assert s_wo == 0.0, s_wo
assert s_wi == 1.0, s_wi
print("OK inyección de control en la réplica: sin=%s con=%s" % (s_wo, s_wi))

# --- 6) construir_evidencia no debe fallar y debe traer las secciones nuevas ---
ejemplos = [{"n": 1, "payload": "PING;64", "status": 200, "response": {"pong": True}}]
sess = {"replay": [
    {"payload": "PING;64", "observado": {"status": 200, "body": {"pong": True}}, "tipo": "replay"},
    {"payload": "CONSULTA;AC-0001;14", "observado": {"status": 200, "body": {"saldo": "0.00"}}},
    {"payload": "CONSULTA;AC-0002;11", "observado": {"status": 200, "body": {"saldo": "400.00"}}},
    {"payload": "CONSULTA;AC-0003;8", "observado": {"status": 404, "body": {"error": "E401"}}},
    {"payload": "CONSULTA;AC-0009;87", "observado": {"status": 404, "body": {"error": "E401"}}},
]}
ev = ag.construir_evidencia(ejemplos, sess)
for seccion in ("PISTAS ARITMÉTICAS", "GRUPOS POR RESULTADO", "TABLA CLAVE", "YA PROBADOS"):
    assert seccion in ev, seccion
assert any("CONSULTA;AC-0001" in l for l in ev.splitlines())
print("OK evidencia con secciones nuevas (PISTAS/GRUPOS/TABLA/YA PROBADOS).")

print("TODAS LAS PRUEBAS PASARON ✔")