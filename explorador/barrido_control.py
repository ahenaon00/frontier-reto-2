"""Fase 2a: barrido de control. Para texto fijo 'PING', prueba controles 00..99
y registra cuales acepta. Cada request se loguea con su hipotesis."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402


def barrer(c, prefijo, seq, rango=range(100)):
    aceptados = []
    for n in rango:
        cc = f"{n:02d}"
        fila = c.msg(f"{prefijo};{cc}", seq,
                     f"¿acepta control {cc} para '{prefijo}'?")
        r = fila["response"]
        err = r.get("error") if isinstance(r, dict) else None
        if err not in ("E201", "E202"):
            aceptados.append((cc, fila["status"], r))
    return aceptados


def main():
    c = Cliente()
    c.reset()
    for pref in ["PING", "PING;"]:
        # sin estado en PING: un solo reset basta
        ac = barrer(c, pref, f"barrido_{pref.replace(';','_')}")
        print(f"{pref!r}: aceptados={[a[0] for a in ac]}")
        for a in ac[:5]:
            print("   ", a)


if __name__ == "__main__":
    main()
