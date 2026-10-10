"""Prueba de integración de main() con modelo y cliente FALSOS (sin red).
Verifica que el ciclo completo corre y que el marcador '?' se sustituye."""
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import agente_matematico as ag

tmp = tempfile.mkdtemp()
ag.PATRONES_JSONL = os.path.join(tmp, "patrones.jsonl")
ag.EJEMPLOS_NUEVOS = os.path.join(tmp, "ejemplos_nuevos.jsonl")
ag.RUTA_DATASET = os.path.join(tmp, "ejemplos.jsonl")
ag.MAX_RONDAS = 3
ag.OPENROUTER_API_KEY = "fake-key-para-test"

# dataset mínimo
with open(ag.RUTA_DATASET, "w", encoding="utf-8") as f:
    f.write(json.dumps({"n": 1, "id": 1, "seq": "ejemplos",
                        "request": {"m": "PING;64"}, "status": 200,
                        "response": {"pong": True}}) + "\n")

# sesión de replay previa (evita fase_recoleccion)
with open(ag.PATRONES_JSONL, "w", encoding="utf-8") as f:
    f.write(json.dumps({"tipo": "reset", "sesion": "replay", "paso": 0,
                        "payload": "__RESET__"}) + "\n")
    f.write(json.dumps({"tipo": "replay", "sesion": "replay", "paso": 1,
                        "payload": "PING;64", "observado": {"status": 200, "body": {"pong": True}}}) + "\n")

llamadas = {"n": 0}


def fake_pedir(evidencia, ronda, feedback):
    llamadas["n"] += 1
    control = "def control(base):\n    tabla = {'PING': '64'}\n    if base.upper() in tabla:\n        return tabla[base.upper()]\n    return str(len(base) % 97)\n"
    replica = "def simular_caja_negra(payload):\n    if payload == '__RESET__':\n        return {'status': 200, 'body': 'ok'}\n    if payload.strip().upper() == 'PING;64':\n        return {'status': 200, 'body': {'pong': True}}\n    if payload.startswith('ALTA;'):\n        return {'status': 201, 'body': {'cuentaId': 'AC-0001'}}\n    return {'status': 400, 'body': {'error': 'E202', 'mensaje': 'control inválido'}}\n"
    return {
        "hipotesis": "pruebo la generalización de mi control en una base nueva",
        "experimentos": [
            {"payload": "ALTA;Nueva;?", "prediccion": {"status": 201, "body": {"cuentaId": "AC-0001"}},
             "motivo": "test de ? con base nueva"},
            {"payload": "PING;64", "prediccion": {"status": 200, "body": {"pong": True}},
             "motivo": "verifico conocido"},
        ],
        "confianza": 0.4,
        "control_candidatas": [control],
        "replica": replica,
    }


class FakeCliente:
    def __init__(self):
        self.calls = []
        self.resets = 0

    def reset(self):
        self.resets += 1

    def msg(self, payload, seq="", hipotesis=""):
        self.calls.append(payload)
        if payload.startswith("ALTA;"):
            return {"status": 201, "response": {"cuentaId": "AC-0001"}}
        if payload.strip().upper() == "PING;64":
            return {"status": 200, "response": {"pong": True}}
        return {"status": 400, "response": {"error": "E202", "mensaje": "control inválido"}}


guardado = {}
ag.pedir_a_ia = fake_pedir
ag.Cliente = FakeCliente
ag._guardar_replica = lambda c: guardado.__setitem__("replica", c)
ag._guardar_control = lambda c: guardado.__setitem__("control", c)

ag.main()

# Verificaciones
cliente = ag.Cliente  # la instancia real está dentro de main; revisamos la clase
print("\n=== VERIFICACIÓN INTEGRACIÓN ===")
assert llamadas["n"] >= 1, "el modelo no fue consultado"
# Comprueba que el experimento con '?' se resolvió y se envió.
regs = ag.Almacen.cargar()
autos = [r for r in regs if r.get("tipo") == "experimento" and r.get("auto")]
assert autos, "no hubo experimento auto-resuelto con '?'"
assert autos[0]["payload"].startswith("ALTA;Nueva;"), autos[0]["payload"]
print("OK experimento '?' resuelto y enviado:", autos[0]["payload"])
assert "control" in guardado and "replica" in guardado, guardado
print("OK main() completó el ciclo y guardó réplica+control.")
print("TODAS LAS VERIFICACIONES DE INTEGRACIÓN PASARON ✔")
