"""¿K depende solo del comando? Modelo sobre argumentos, K por comando."""
import sys
sys.path.insert(0, __file__.rsplit("explorador", 1)[0] + "explorador")
from ajuste97 import DATOS  # noqa: E402

M, B, A = 97, 10, 94


def S(t):
    return sum(ord(c) * pow(B, len(t) - 1 - i, M) for i, c in enumerate(t)) % M


FILT = {
    "args_alnum": lambda a: "".join(c for c in a if c.isalnum()),
    "args_con;": lambda a: a.replace("-", "").replace("_", ""),
    "args_todo": lambda a: a,
}
for nombre, f in FILT.items():
    print("==", nombre)
    por_cmd = {}
    for t, cc in DATOS:
        cmd, args = t.split(";", 1)
        k = (cc - A * S(f(args))) % M
        por_cmd.setdefault(cmd, []).append(k)
    for cmd, ks in por_cmd.items():
        print(f"  {cmd:10} {ks}  {'CONSTANTE' if len(set(ks)) == 1 else ''}")
