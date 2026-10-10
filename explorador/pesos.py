"""Fase 2b: peso por posicion. Base 'CONSULTA;AC-0001' (cc=14). Cambia un caracter
de la parte 'AC-0001' (posiciones 9..15) y barre 00..96 hasta que deje de dar E202.
Para en cuanto encuentra el control valido."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402

BASE = "CONSULTA;AC-0001"
CAMBIOS = {9: "B", 10: "D", 11: "_", 12: "1", 13: "1", 14: "1", 15: "2"}


def buscar_cc(c, texto, seq, hip):
    for n in range(100):
        cc = f"{n:02d}"
        fila = c.msg(f"{texto};{cc}", seq, f"{hip} (probando cc={cc})")
        r = fila["response"]
        err = r.get("error") if isinstance(r, dict) else None
        if err not in ("E201", "E202"):
            return cc, fila
    return None, None


def main():
    c = Cliente()
    c.reset()
    c.msg("ALTA;Lucia;82", "pesos", "preparar cuenta")
    salida = {}
    for pos, ch in CAMBIOS.items():
        t = BASE[:pos] + ch + BASE[pos + 1:]
        cc, fila = buscar_cc(c, t, "pesos", f"peso posicion {pos}: {BASE[pos]!r}->{ch!r}")
        salida[pos] = (t, cc, fila["response"] if fila else None)
        print(pos, repr(t), "cc=", cc, fila["response"] if fila else None, flush=True)
    pathlib.Path(__file__).with_name("pesos_resultado.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
