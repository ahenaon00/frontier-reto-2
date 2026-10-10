import os, sys
os.environ.setdefault("FRONTIER_TOKEN", "TOKEN_TEST")
from fastapi.testclient import TestClient
import importlib.util
spec = importlib.util.spec_from_file_location("entrypoint", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrypoint.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
c = TestClient(mod.app)
H = {"Authorization": "Bearer TOKEN_TEST"}

r = c.get("/health")
print("health", r.status_code)

r = c.post("/__reset", headers=H)
print("reset", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "PING;64"})
print("PING;64", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "ALTA;Lucia;82"})
print("ALTA;Lucia;82", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "CONSULTA;AC-0001;14"})
print("CONSULTA;AC-0001;14", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "DEPOSITO;AC-0001;250000;86"})
print("DEPOSITO", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "CONSULTA;AC-0001;14"})
print("CONSULTA2", r.status_code, r.text)

r = c.post("/msg", headers=H, json={"m": "ALTA;Lucia;83"})
print("ALTA mal control", r.status_code, r.text)

r = c.post("/msg", json={"m": "PING;64"})  # sin token
print("sin token", r.status_code)
r = c.post("/msg", headers={"Authorization": "Bearer OTRO"}, json={"m": "PING;64"})
print("token ajeno", r.status_code)
r = c.post("/msg", headers=H, content=b"PING;64")  # body crudo (no JSON)
print("body crudo", r.status_code, r.text)
