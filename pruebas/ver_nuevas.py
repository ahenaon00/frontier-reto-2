import json, os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exp = [json.loads(l) for l in open(os.path.join(RAIZ, "experimentos.jsonl"), encoding="utf-8")]
print("total filas:", len(exp))
print("=== filas nuevas (id > 1930) ===")
for r in exp:
    if r["id"] > 1930:
        print("id=%s seq=%s req=%r -> %s %s | %s" % (
            r["id"], r["seq"], (r.get("request") or {}).get("m"), r["status"],
            json.dumps(r["response"], ensure_ascii=False), r.get("hipotesis", "")[:70]))
