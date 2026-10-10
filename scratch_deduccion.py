import json

def cargar_casos_empiricos(ruta):
    casos = []
    with open(ruta, 'r', encoding='utf-8') as f:
        for linea in f:
            if not linea.strip(): continue
            d = json.loads(linea)
            if d['status'] in [200, 201]:
                m = d['request']['m'].split(';')
                casos.append({'payload': d['request']['m'], 'comando': m[0], 'args': ';'.join(m[1:-1]), 'control': int(m[-1])})
    return casos

def horner_hash(s):
    h = 0
    for char in s:
        h = (h * 31 + ord(char)) % 97
    return h

casos = cargar_casos_empiricos('pruebas/ejemplos.jsonl')
for c in casos:
    # Intento 1: Horner directo
    h1 = horner_hash(c['comando'] + c['args'])
    # Intento 2: Solo args
    h2 = horner_hash(c['args'])
    print(f"[{c['comando']}] Args: {c['args']} | Control: {c['control']} | H1: {h1} | H2: {h2}")
