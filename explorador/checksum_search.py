"""Busca offline el algoritmo del campo de control usando ejemplos.jsonl.

Cada mensaje tiene forma CMD;a;b;...;CC. Un mensaje es "valido" si el servidor
no responde E201/E202 (control). Probamos funciones candidatas sobre el texto
previo al ultimo ';' (con y sin el ';') y vemos cuales concuerdan con TODOS.
"""
import json
import pathlib
import re

RUTA = pathlib.Path(__file__).resolve().parent.parent / "pruebas" / "ejemplos.jsonl"


def cargar():
    filas = []
    for linea in RUTA.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            filas.append(json.loads(linea))
    return filas


def etiqueta(fila):
    """True=control valido, False=E202, None=E201 (mal formado) o ambiguo."""
    r = fila["response"]
    err = r.get("error") if isinstance(r, dict) else None
    if err == "E202":
        return False
    if err == "E201":
        return None
    return True


def cuerpos(m):
    """Variantes del texto sobre el que se calcula el control."""
    if ";" not in m:
        return {}
    base, cc = m.rsplit(";", 1)
    return {
        "sin_cc": base,
        "con_sep": base + ";",
        "sin_cmd": base.split(";", 1)[1] if ";" in base else "",
        "upper": base.upper(),
        "campos_sin_sep": base.replace(";", ""),
    }


def candidatos():
    sumas = {
        "sum_ascii": lambda s: sum(s.encode()),
        "sum_pos": lambda s: sum((i + 1) * b for i, b in enumerate(s.encode())),
        "sum_pos0": lambda s: sum(i * b for i, b in enumerate(s.encode())),
        "len": lambda s: len(s),
        "xor": lambda s: __import__("functools").reduce(lambda a, b: a ^ b, s.encode(), 0),
        "sum_digitos": lambda s: sum(int(c) for c in s if c.isdigit()),
        "sum_alt": lambda s: sum(b * (1 if i % 2 == 0 else 3) for i, b in enumerate(s.encode())),
        "poly31": lambda s: __import__("functools").reduce(lambda h, b: h * 31 + b, s.encode(), 0),
        "poly33": lambda s: __import__("functools").reduce(lambda h, b: h * 33 + b, s.encode(), 5381),
    }
    mods = [97, 100, 99, 101, 89, 91, 256]
    for nombre, f in sumas.items():
        for md in mods:
            for off in (0, 1):
                yield f"{nombre}%{md}+{off}", (lambda s, f=f, md=md, off=off: (f(s) + off) % md)


def main():
    filas = cargar()
    datos = []
    for fila in filas:
        m = fila["request"]["m"]
        if ";" not in m:
            continue
        cc = m.rsplit(";", 1)[1]
        tag = etiqueta(fila)
        # Solo sabemos que CC es correcto si NO hubo error de control
        # (excepto E301/E302 que se evaluan despues o antes: ver reporte)
        datos.append((m, cc, tag, fila["response"]))
    print("Muestras:")
    for m, cc, tag, resp in datos:
        print(f"  {m!r:45} cc={cc} control_ok={tag} resp={resp}")

    validos = [(m, cc) for m, cc, tag, _ in datos if tag is True and re.fullmatch(r"\d\d", cc)]
    invalidos = [(m, cc) for m, cc, tag, _ in datos if tag is False]
    print(f"\nvalidos={len(validos)} invalidos(E202)={len(invalidos)}")

    hallados = []
    for nombre_c, fn in candidatos():
        for var in ["sin_cc", "con_sep", "sin_cmd", "upper", "campos_sin_sep"]:
            ok = True
            for m, cc in validos:
                cuerpo = cuerpos(m).get(var)
                if cuerpo is None or fn(cuerpo) != int(cc):
                    ok = False
                    break
            if ok:
                for m, cc in invalidos:
                    cuerpo = cuerpos(m).get(var)
                    if cuerpo is not None and fn(cuerpo) == int(cc):
                        ok = False
                        break
            if ok:
                hallados.append((nombre_c, var))
    print("\nCandidatos consistentes:", hallados or "ninguno")


if __name__ == "__main__":
    main()
