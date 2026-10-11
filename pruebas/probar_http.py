import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
import entrypoint

c = TestClient(entrypoint.app)

def m(label, **kw):
    r = c.request(**kw)
    print("%-40s -> %s %s" % (label, r.status_code, r.text))

m("GET /health sin token", method="GET", url="/health")
m("GET /health con token", method="GET", url="/health", headers={"Authorization": "Bearer cualquiera"})
m("POST /__reset sin token", method="POST", url="/__reset")
m("POST /__reset token ajeno", method="POST", url="/__reset", headers={"Authorization": "Bearer ajeno-123"})
m("POST /__reset token .env", method="POST", url="/__reset", headers={"Authorization": "Bearer cn-p-abh_bog_e6f6_y4af-8FpokEfCkqN6u8xUZuGVzs"})
m("POST /msg sin token", method="POST", url="/msg", json={"m": "PING;64"})
m("POST /msg token ajeno PING;64", method="POST", url="/msg", headers={"Authorization": "Bearer ajeno-123"}, json={"m": "PING;64"})
m("GET /nope token ajeno", method="GET", url="/nope", headers={"Authorization": "Bearer ajeno-123"})
m("GET /nope sin token", method="GET", url="/nope")
m("POST /msg ALTA;Lucia;82", method="POST", url="/msg", headers={"Authorization": "Bearer x"}, json={"m": "ALTA;Lucia;82"})
m("POST /msg CONSULTA;AC-0001;14", method="POST", url="/msg", headers={"Authorization": "Bearer x"}, json={"m": "CONSULTA;AC-0001;14"})
