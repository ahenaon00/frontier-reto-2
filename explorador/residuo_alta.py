"""Residuo de ALTA: s_efectivo = (cc - 82 - 94*H) / 10^m (mod 97), por muestra."""
M = 97
ALTA = [("Lucia", 82), ("Mateo", 3), ("Ana", 50), ("Anb", 47), ("Aoa", 20), ("Bna", 57),
        ("Anaa", 3), ("aaaaa", 30), ("baaaa", 3), ("abaaa", 37), ("aabaa", 21),
        ("aaaba", 97), ("aaaab", 27), ("ana", 50), ("bna", 57)]


def H(s):
    h = 0
    for c in s.lower():
        h = (h * 10 + ord(c)) % M
    return h


for nombre, cc in ALTA:
    m = len(nombre)
    s = ((cc - 82 - 94 * H(nombre)) * pow(pow(10, m, M), -1, M)) % M
    print(f"{nombre:7} m={m} cc={cc:3} H={H(nombre):3} s_efectivo={s}")
