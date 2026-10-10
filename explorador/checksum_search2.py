"""Busqueda ampliada: cc = (K +/- sum((A + B*i) * ord(c))) % M.

Para cada combinacion (variante de texto, A, B, M, direccion del indice) se
calcula S por mensaje valido y se comprueba si (cc -/+ S) % M es constante K.
Ademas se verifica que el unico invalido (E202) NO cumpla esa K.
"""
import re
import sys

sys.path.insert(0, __file__.rsplit("explorador", 1)[0] + "explorador")
from checksum_search import cargar, etiqueta, cuerpos  # noqa: E402


def main():
    filas = cargar()
    validos, invalidos = [], []
    for f in filas:
        m = f["request"]["m"]
        if ";" not in m:
            continue
        cc = m.rsplit(";", 1)[1]
        t = etiqueta(f)
        if t is True and re.fullmatch(r"\d{1,2}", cc):
            validos.append((m, int(cc)))
        elif t is False:
            invalidos.append((m, int(cc)))
    # dedup
    validos = list(dict.fromkeys(validos))

    hallazgos = []
    variantes = ["sin_cc", "con_sep", "sin_cmd", "upper", "campos_sin_sep"]
    for var in variantes:
        textos = [(cuerpos(m)[var], cc) for m, cc in validos]
        textos_inv = [(cuerpos(m)[var], cc) for m, cc in invalidos]
        for desde_fin in (False, True):
            for M in (97, 100, 101, 89, 103, 256, 99, 98, 128):
                for A in range(0, 40):
                    for B in range(0, 40):
                        def S(t):
                            bs = t.encode()
                            n = len(bs)
                            tot = 0
                            for i, b in enumerate(bs):
                                idx = (n - 1 - i) if desde_fin else i
                                tot += (A + B * idx) * b
                            return tot
                        for signo in (1, -1):
                            Ks = {(cc - signo * S(t)) % M for t, cc in textos}
                            if len(Ks) == 1:
                                K = Ks.pop()
                                if all((cc - signo * S(t)) % M != K for t, cc in textos_inv):
                                    hallazgos.append((var, desde_fin, M, A, B, signo, K))
    print(f"{len(hallazgos)} candidatos")
    for h in hallazgos[:40]:
        print("var=%s desde_fin=%s M=%d A=%d B=%d signo=%+d K=%d" % h)


if __name__ == "__main__":
    main()
