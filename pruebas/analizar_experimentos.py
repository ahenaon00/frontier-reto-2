import json, collections

rows = [json.loads(l) for l in open("experimentos.jsonl", encoding="utf-8")]

# Comando normalizado
def cmd(m):
    return (m or "").split(";")[0].upper()

print("== comandos ==")
print(collections.Counter(cmd(r["request"].get("m", "")) for r in rows).most_common())

print("\n== (status, error) ==")
c = collections.Counter()
for r in rows:
    resp = r.get("response")
    err = resp.get("error") if isinstance(resp, dict) else None
    c[(r["status"], err)] += 1
print(c.most_common())

print("\n== ejemplo por (status,error) ==")
seen = set()
for r in rows:
    resp = r.get("response")
    err = resp.get("error") if isinstance(resp, dict) else None
    key = (r["status"], err)
    if key in seen:
        continue
    seen.add(key)
    print("id=%s status=%s req=%r resp=%r" % (r["id"], r["status"], r["request"].get("m"), resp))

print("\n== formas de respuesta 2xx ==")
shapes = collections.Counter()
for r in rows:
    resp = r.get("response")
    if isinstance(resp, dict):
        shapes[tuple(sorted(resp.keys()))] += 1
for k, v in shapes.most_common():
    print(k, v)
