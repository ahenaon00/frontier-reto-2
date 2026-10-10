"""¿Desborde antes del mod 97? Probar hash H = sum(ord*10^idx) reducido a distintos anchos."""
import sys
sys.path.insert(0, __file__.rsplit("explorador", 1)[0] + "explorador")
from ajuste97 import DATOS, FILTROS  # noqa: E402

M, A = 97, 94


def horner_wrap(t, B, W, signed=False):
    h = 0
    for c in t:
        h = (h * B + ord(c))
        h %= W
    if signed and h >= W // 2:
        h -= W
    return h


def main():
    anchos = {"2^31": 2**31, "2^32": 2**32, "2^53": 2**53, "2^63": 2**63, "2^64": 2**64,
              "1e9+7": 10**9 + 7, "1e6": 10**6, "1e5": 10**5, "1e4": 10**4,
              "2^16": 2**16, "2^24": 2**24, "2^20": 2**20, "999983": 999983, "100003": 100003}
    for nombre_f, filt in FILTROS.items():
        for nombre_w, W in anchos.items():
            for signed in (False, True):
                for A_ in (94, 1, 3, 97 - 3):
                    for inv in (1, -1):
                        Ks = set()
                        for t, cc in DATOS:
                            h = horner_wrap(filt(t), 10, W, signed)
                            Ks.add((cc - inv * A_ * h) % M)
                            if len(Ks) > 1:
                                break
                        if len(Ks) == 1:
                            print("OK", nombre_f, nombre_w, "signed" if signed else "", "a=", inv * A_, "K=", Ks)
    print("fin")


main()
