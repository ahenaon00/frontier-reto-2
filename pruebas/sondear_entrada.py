"""Sondea rutas, autenticación y forma del cuerpo del original y lo registra
en experimentos.jsonl (seq 'entrada'). Usa el cliente instrumentado."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from explorador.cliente import Cliente

c = Cliente()
SEQ = "entrada"


def reg(metodo, ruta, cuerpo, hipotesis, conclusion=None, headers=None, con_token=True):
    status, texto, hl = c.crudo(metodo, ruta, cuerpo, headers, con_token)
    req = {"metodo": metodo, "ruta": ruta, "cuerpo": cuerpo}
    fila = c._log(SEQ, hipotesis, req, status, c._parse(texto), hl.get("x-req"), conclusion)
    print("%-4s %-10s -> %s %s" % (metodo, ruta, status, texto[:80]))
    return fila


# 0) comprobar que el token sigue vivo
f = reg("GET", "/health", None, "comprobar que el token sigue activo: GET /health con token",
        "200 confirma que el token sigue vigente", )
if f["status"] != 200:
    print("[!] El token ya no sirve (status %s). Abortando sin seguir gastando." % f["status"])
    sys.exit(0)

# 1) rutas y autenticación
reg("GET", "/health", None, "GET /health SIN token",
    "exige token: responde 401 E001 no autorizado", con_token=False)
reg("POST", "/__reset", None, "POST /__reset con token",
    "reinicia el estado del token y responde 200 {'ok':true}")
reg("POST", "/__reset", None, "POST /__reset SIN token",
    "responde 401 E001 no autorizado", con_token=False)
reg("POST", "/__reset", None, "POST /__reset con token ajeno",
    "un token que no existe responde 401 E001", headers={"Authorization": "Bearer token-ajeno"})
reg("GET", "/nope", None, "GET ruta inexistente con token",
    "ruta desconocida -> 404 E404 'ruta desconocida'")
reg("POST", "/nope", {"m": "PING;64"}, "POST ruta inexistente con token",
    "cualquier método en ruta desconocida -> 404 E404")
reg("POST", "/msg", {"m": "PING;64"}, "POST /msg SIN token",
    "responde 401 E001", con_token=False)
reg("POST", "/msg", {"m": "PING;64"}, "POST /msg con token ajeno",
    "responde 401 E001", headers={"Authorization": "Bearer token-ajeno"})

# 2) forma del cuerpo
reg("POST", "/msg", "no-json", "cuerpo que NO es JSON",
    "ver qué hace el servicio con un cuerpo no JSON")
reg("POST", "/msg", '{"x":1}', "JSON sin la clave m",
    "ver qué responde si falta 'm'")
reg("POST", "/msg", '{"m":123}', "m que no es string (numero)",
    "ver si castea o falla")
reg("POST", "/msg", None, "sin cuerpo",
    "ver qué responde sin cuerpo")
reg("POST", "/msg", '{"m":""}', "m vacio",
    "ver la validacion de integridad con payload vacio")
reg("POST", "/msg", {"m": "PING;64"}, "cuerpo JSON valido de control",
    "control de cordura: 200 {'pong':true}")

print("\n[OK] evidencia de entrada registrada en experimentos.jsonl (seq=%s)" % SEQ)
