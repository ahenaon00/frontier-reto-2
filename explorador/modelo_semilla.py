"""Modelo con semilla por comando, plegando mayusculas y con 0 -> 97.
   cc = ((C0 + 94*H(args) + 10^m * s_cmd) mod 97) ; si 0 -> 97"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ajuste97 import DATOS  # noqa: E402

M = 97
AQUI = pathlib.Path(__file__).parent
MUESTRAS = list(DATOS)
for nombre in ("pesos_cmds.json", "pesos_alta.json"):
    p = AQUI / nombre
    if p.exists():
        for t, v in json.loads(p.read_text()).items():
            cc = v[0]
            if cc is not None:
                MUESTRAS.append((t, cc))
MUESTRAS += [("ALTA;aaaba", 97), ("ALTA;ana", 50), ("ALTA;Bna", 57), ("ALTA;bna", 57)]
MUESTRAS = list(dict.fromkeys(MUESTRAS))

PLEGADOS = {"lower": str.lower, "upper": str.upper, "ninguno": lambda s: s}


def H(args, fold):
    h = 0
    for c in fold(args):
        if c.isalnum():
            h = (h * 10 + ord(c)) % M
    return h


def m_de(args):
    return sum(c.isalnum() for c in args)


def a_rango(x):
    return M if x % M == 0 else x % M


def main():
    for nf, fold in PLEGADOS.items():
        print("=== pliegue:", nf)
        por_cmd = {}
        for t, cc in MUESTRAS:
            cmd, args = t.split(";", 1)
            por_cmd.setdefault(cmd.upper(), []).append((t, args, cc))
        for cmd, lst in por_cmd.items():
            t, args, cc = lst[0]
            num = (cc - 82 - 94 * H(args, fold)) % M
            s = num * pow(pow(10, m_de(args), M), -1, M) % M
            malos = []
            for t, args, cc in lst:
                pred = a_rango((82 + 94 * H(args, fold) + pow(10, m_de(args), M) * s))
                if pred != cc:
                    malos.append((t, cc, pred))
            print(f"{cmd:9} s={s:3} muestras={len(lst):2} fallos={len(malos)}")
            for x in malos[:6]:
                print("     FALLA", x)


if __name__ == "__main__":
    main()
