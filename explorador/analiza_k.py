"""K por muestra con todos los datos nuevos: K = cc + 3*h mod 97, h = Horner base 10 sobre alfanumericos."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ajuste97 import DATOS  # noqa: E402

M = 97


def h_de(texto, filtro):
    h = 0
    for c in texto:
        if filtro(c):
            h = (h * 10 + ord(c)) % M
    return h


nuevos = json.loads(pathlib.Path(__file__).with_name("pesos_cmds.json").read_text())
muestras = list(DATOS) + [(t, v[0]) for t, v in nuevos.items() if v[0] is not None]
muestras = list(dict.fromkeys(muestras))

FILTROS = {
    "alnum": lambda c: c.isalnum(),
    "alnum+;": lambda c: c.isalnum() or c == ";",
}
for nf, f in FILTROS.items():
    print("==", nf)
    por_cmd = {}
    for t, cc in muestras:
        cmd = t.split(";")[0].upper()
        k = (cc + 3 * h_de(t, f)) % M
        por_cmd.setdefault(cmd, []).append((t, k))
    for cmd, lst in por_cmd.items():
        print(f"  {cmd}")
        for t, k in lst:
            print(f"     K={k:3}  {t}")
