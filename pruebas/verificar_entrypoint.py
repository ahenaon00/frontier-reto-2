import sys, types, json, importlib.util, os

# --- stub de fastapi para poder importar entrypoint sin dependencias ---
fake = types.ModuleType("fastapi")
class _FastAPI:
    def get(self, *a, **k): return lambda f: f
    def post(self, *a, **k): return lambda f: f
    def api_route(self, *a, **k): return lambda f: f
fake.FastAPI = _FastAPI
fake.Request = object
fake.Response = object
fake.Header = lambda *a, **k: None
resp = types.ModuleType("fastapi.responses")
resp.JSONResponse = object
resp.PlainTextResponse = object
sys.modules["fastapi"] = fake
sys.modules["fastapi.responses"] = resp

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("entrypoint", os.path.join(RAIZ, "entrypoint.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ev = [json.loads(l) for l in open(os.path.join(RAIZ, "patrones_encontrados.jsonl"), encoding="utf-8")]

# 1) secuencia replay = verdad actual del servicio (una sola sesión)
replay = sorted([r for r in ev if r.get("tipo") == "replay"], key=lambda r: r.get("paso", 0))
mod.reset_estado()
ok = tot = 0
fallos = []
for r in replay:
    tot += 1
    out = mod.simular_caja_negra(r["payload"])
    obs = r["observado"]
    if out["status"] == obs["status"] and out["body"] == obs["body"]:
        ok += 1
    else:
        fallos.append((r["payload"], obs, out))
print("REPLAY (verdad actual): %d/%d" % (ok, tot))
for p, obs, out in fallos:
    print("  MISMATCH", p)
    print("    esperado:", obs["status"], json.dumps(obs["body"], ensure_ascii=False))
    print("    obtenido:", out["status"], json.dumps(out["body"], ensure_ascii=False))

# 2) todos los pares base->control aceptados (replay + experimentos)
pares = {}
for r in ev:
    p = r.get("payload", "")
    if ";" not in p:
        base, ctrl = p, ""
    else:
        base, ctrl = p.rsplit(";", 1)
    obs = r.get("observado", {})
    body = obs.get("body", {})
    if isinstance(body, dict) and body.get("error") in ("E201", "E202"):
        continue  # control rechazado: no sirve como par
    if ctrl.isdigit():
        pares[base.upper()] = ctrl
mal = 0
for base, ctrl in sorted(pares.items()):
    got = mod.control(base)
    if got != ctrl:
        mal += 1
        print("  CONTROL MAL: %-40s esperado %s -> %s" % (base, ctrl, got))
print("CONTROL: %d pares, %d mal" % (len(pares), mal))
