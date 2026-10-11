import json, collections, os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    p = os.path.join(RAIZ, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")]


exp = load("experimentos.jsonl")
pat = load("patrones_encontrados.jsonl")

print("=== patrones tipo replay (verdad actual tras reset) ===")
for r in [x for x in pat if x.get("tipo") == "replay"]:
    print(r.get("paso"), r.get("payload"), "->", json.dumps(r.get("observado"), ensure_ascii=False))

print("\n=== saldo: formas observadas recientes ===")
sal = collections.Counter()
ej = {}
for r in exp:
    resp = r.get("response")
    if isinstance(resp, dict) and "saldo" in resp:
        key = type(resp["saldo"]).__name__
        sal[key] += 1
        ej.setdefault(key, (r["id"], r["request"].get("m"), resp))
print(sal)
for k, v in ej.items():
    print("  tipo", k, "ej id=%s req=%r resp=%r" % v)

print("\n=== E301 (comando desconocido) ejemplos ===")
n = 0
for r in exp:
    resp = r.get("response")
    if isinstance(resp, dict) and resp.get("error") == "E301":
        print("  id=%s req=%r -> %s %r" % (r["id"], r["request"].get("m"), r["status"], resp))
        n += 1
        if n >= 8:
            break

print("\n=== E202 cuyo comando es desconocido (control ANTES que comando) ===")
n = 0
for r in exp:
    resp = r.get("response")
    m = (r["request"].get("m") or "")
    cmd = m.split(";")[0].upper()
    conocidos = ("PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA")
    if isinstance(resp, dict) and resp.get("error") == "E202" and cmd not in conocidos:
        print("  id=%s req=%r -> %s %r" % (r["id"], m, r["status"], resp))
        n += 1
        if n >= 8:
            break
if not n:
    print("  (ninguno)")

print("\n=== comando en minusculas/mixto que tuvo exito (case-insensitive) ===")
n = 0
for r in exp:
    m = (r["request"].get("m") or "")
    cmd = m.split(";")[0]
    if cmd and cmd != cmd.upper() and 200 <= (r["status"] or 0) < 300:
        print("  id=%s req=%r -> %s %r" % (r["id"], m, r["status"], r["response"]))
        n += 1
        if n >= 6:
            break
if not n:
    print("  (ninguno)")

print("\n=== sesiones con ALTA..DEPOSITO..CONSULTA..ANULA (memoria) ===")
ses = collections.defaultdict(list)
for r in exp:
    ses[r["seq"]].append(r)
for sid, filas in ses.items():
    cmds = [f["request"].get("m", "?").split(";")[0].upper() for f in filas]
    if "ALTA" in cmds and "ANULA" in cmds and "CONSULTA" in cmds:
        print("  seq=%s (%d filas):" % (sid, len(filas)))
        for f in filas:
            print("    id=%s %r -> %s %s" % (f["id"], f["request"].get("m"), f["status"], json.dumps(f["response"], ensure_ascii=False)[:90]))
        break

print("\n=== TRANSFER >=100000 (E506) y E507 ===")
n = 0
for r in exp:
    resp = r.get("response")
    if isinstance(resp, dict) and resp.get("error") in ("E506", "E507"):
        print("  id=%s req=%r -> %s %r" % (r["id"], r["request"].get("m"), r["status"], resp))
        n += 1
        if n >= 6:
            break

print("\n=== ya anulada ===")
for r in exp:
    resp = r.get("response")
    if isinstance(resp, dict) and resp.get("motivo") == "ya anulada":
        print("  id=%s req=%r -> %s %r" % (r["id"], r["request"].get("m"), r["status"], resp))
        break

print("\n=== E104 / E103 ejemplos ===")
vistos = set()
for r in exp:
    resp = r.get("response")
    if isinstance(resp, dict) and resp.get("error") in ("E103", "E104") and resp["error"] not in vistos:
        vistos.add(resp["error"])
        print("  id=%s req=%r -> %s %r" % (r["id"], r["request"].get("m"), r["status"], resp))
