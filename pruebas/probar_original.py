import json, urllib.request, urllib.error

ORIG = "https://caja-negra-production-c64f.up.railway.app"
TOK = "cn-p-abh_bog_e6f6_y4af-8FpokEfCkqN6u8xUZuGVzs"


def call(metodo, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(ORIG + path, data=data, method=metodo)
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return "ERR", str(e)


print("GET  /health +token   ", call("GET", "/health", token=TOK))
print("GET  /nope   +token   ", call("GET", "/nope", token=TOK))
print("POST /nope   +token   ", call("POST", "/nope", token=TOK, body={"m": "PING;64"}))
print("POST /msg    +token   ", call("POST", "/msg", token=TOK, body={"m": "PING;64"}))
print("POST /__reset +token  ", call("POST", "/__reset", token=TOK))
