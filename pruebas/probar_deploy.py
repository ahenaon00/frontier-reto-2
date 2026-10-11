import json, sys, time, urllib.request, urllib.error

LIVE = "https://frontier-reto-2-production-c5d4.up.railway.app"
TOK_ENV = "cn-p-abh_bog_e6f6_y4af-8FpokEfCkqN6u8xUZuGVzs"


def call(metodo, path, token=None, body=None, timeout=25):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(LIVE + path, data=data, method=metodo)
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return "ERR", str(e)


def esperar_version(limite=40):
    for i in range(limite):
        st, _ = call("POST", "/__reset", token="token-ajeno-abc")
        if st == 200:
            print("Nueva version desplegada tras %d intentos" % (i + 1))
            return True
        print("  ...intento %d: /__reset token ajeno -> %s" % (i + 1, st))
        time.sleep(6)
    return False


if not esperar_version():
    print("TIMEOUT esperando el despliegue")
    sys.exit(1)

casos = [
    ("GET /health sin token", "GET", "/health", None, None),
    ("POST /__reset sin token", "POST", "/__reset", None, None),
    ("POST /__reset token ajeno", "POST", "/__reset", "token-ajeno-abc", None),
    ("POST /__reset token .env", "POST", "/__reset", TOK_ENV, None),
    ("POST /msg sin token", "POST", "/msg", None, {"m": "PING;64"}),
    ("POST /msg token ajeno PING;64", "POST", "/msg", "token-ajeno-abc", {"m": "PING;64"}),
    ("POST /msg .env ALTA;Lucia;82", "POST", "/msg", TOK_ENV, {"m": "ALTA;Lucia;82"}),
    ("POST /msg .env CONSULTA;AC-0001;14", "POST", "/msg", TOK_ENV, {"m": "CONSULTA;AC-0001;14"}),
    ("GET /nope con token", "GET", "/nope", TOK_ENV, None),
    ("GET /nope sin token", "GET", "/nope", None, None),
]
for label, met, path, tok, body in casos:
    st, tx = call(met, path, token=tok, body=body)
    print("%-38s -> %s %s" % (label, st, tx))
