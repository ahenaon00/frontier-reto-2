import json, os, collections

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exp = [json.loads(l) for l in open(os.path.join(RAIZ, "experimentos.jsonl"), encoding="utf-8")]


def m(r):
    x = r.get("request")
    return x.get("m") if isinstance(x, dict) else None


print("=== id=1515 contexto (seq y vecinos) ===")
for r in exp:
    if r["id"] == 1515:
        sid = r["seq"]
        print("seq:", sid)
        vecinos = [x for x in exp if x["seq"] == sid]
        for v in sorted(vecinos, key=lambda x: x["id"]):
            print("  id=%s %r -> %s %s" % (v["id"], m(v), v["status"], json.dumps(v["response"], ensure_ascii=False)[:80]))
        break

print("\n=== TRANSFER 100000 -> E506 (actual) ===")
for r in exp:
    if m(r) == "TRANSFER;AC-0001;AC-0002;100000;12":
        print("  id=%s seq=%s -> %s %s" % (r["id"], r["seq"], r["status"], json.dumps(r["response"], ensure_ascii=False)))

print("\n=== seqs distintos (para elegir sesion de memoria actual) ===")
byseq = collections.defaultdict(list)
for r in exp:
    byseq[r["seq"]].append(r)
for sid, filas in byseq.items():
    cmds = [ (m(x) or "").split(";")[0].upper() for x in filas ]
    if "ALTA" in cmds and "ANULA" in cmds:
        tiene_str = any(isinstance(x.get("response"), dict) and isinstance(x["response"].get("saldo"), str) for x in filas)
        print("  seq=%s filas=%d saldo_str=%s" % (sid, len(filas), tiene_str))
