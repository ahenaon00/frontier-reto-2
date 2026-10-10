"""ALTA: peso por posicion en un nombre de 5 letras minusculas, y efecto de mayuscula.
Base 'ALTA;aaaaa'; variantes: +1 en cada posicion; 'Aaaaa' (mayuscula inicial).
Tope duro de requests."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402
from barrido_comandos import Presupuesto, barrer, predecir  # noqa: E402

BASE = "ALTA;aaaaa"
VARIANTES = ["ALTA;baaaa", "ALTA;abaaa", "ALTA;aabaa", "ALTA;aaaba", "ALTA;aaaab", "ALTA;Aaaaa"]


def main():
    c = Cliente()
    c.reset()
    pres = Presupuesto(450)
    res = {}
    try:
        cc0, f0, ev0 = barrer(c, pres, BASE, "pesos_ALTA2", f"ALTA base {BASE!r}")
        print("base", BASE, cc0, ev0, flush=True)
        res[BASE] = (cc0, ev0)
        for v in VARIANTES:
            try:
                pred = predecir(cc0, BASE, v)
            except StopIteration:
                pred = None
            cc, f, ev = barrer(c, pres, v, "pesos_ALTA2", f"ALTA variante {v!r}", pred)
            print(f"  {v!r:14} cc={cc} predicho={pred} acierto={cc == pred} (usado {pres.usado})", flush=True)
            res[v] = (cc, ev)
    except RuntimeError as e:
        print("PARADO:", e)
    c.reset()
    pathlib.Path(__file__).with_name("pesos_alta.json").write_text(json.dumps(res, indent=1))
    print("requests:", pres.usado)


if __name__ == "__main__":
    main()
