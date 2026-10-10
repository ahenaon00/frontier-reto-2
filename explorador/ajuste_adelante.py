"""Ajuste hacia adelante: cc = (K + a * sum(ord(c_i) * r^i)) mod 97, i desde el INICIO.
Datos: todos los pares conocidos (ejemplos + barridos). Prueba filtros y todas las (r, a)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ajuste97 import DATOS  # noqa: E402

M = 97
nuevos = json.loads(pathlib.Path(__file__).with_name("pesos_cmds.json").read_text())
MUESTRAS = list(dict.fromkeys(list(DATOS) + [(t, v[0]) for t, v in nuevos.items() if v[0] is not None]))

FILTROS = {
    "alnum": lambda t: "".join(c for c in t if c.isalnum()),
    "alnum+;": lambda t: "".join(c for c in t if c.isalnum() or c == ";"),
    "sin -_": lambda t: t.replace("-", "").replace("_", ""),
    "sin -_;": lambda t: t.replace("-", "").replace("_", "").replace(";", ""),
    "args_alnum": lambda t: "".join(c for c in t.split(";", 1)[1] if c.isalnum()),
    "args+;": lambda t: "".join(c for c in t.split(";", 1)[1] if c.isalnum() or c == ";"),
}


def main():
    total = 0
    for nombre, f in FILTROS.items():
        textos = [(f(t), cc) for t, cc in MUESTRAS]
        for r in range(1, M):
            pot = [pow(r, i, M) for i in range(80)]
            S = [sum(ord(c) * pot[i] for i, c in enumerate(t)) % M for t, _ in textos]
            for a in range(1, M):
                K = (textos[0][1] - a * S[0]) % M
                if all((K + a * s) % M == cc % M for s, (_, cc) in zip(S, textos)):
                    print(f"OK filtro={nombre} r={r} a={a} K={K}")
                    total += 1
    print("candidatos:", total)


if __name__ == "__main__":
    main()
