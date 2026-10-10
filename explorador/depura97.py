"""Depura el modelo cc = (K + 94 * sum(ord * 10^idx_final)) % 97 por comando."""
DATOS = [
    ("ALTA;Lucia", 82), ("ALTA;Mateo", 3),
    ("CONSULTA;AC-0001", 14), ("CONSULTA;AC-0002", 11), ("CONSULTA;AC-0009", 87),
    ("CONSULTA;AC-0101", 5),
    ("DEPOSITO;AC-0001;250000", 86), ("DEPOSITO;AC-0002;700", 35),
    ("TRANSFER;AC-0001;AC-0002;40000", 86), ("TRANSFER;AC-0001;AC-0002;100000", 12),
    ("TRANSFER;AC-0001;AC-0002;120000", 55), ("TRANSFER;AC-0002;AC-0001;50000", 23),
    ("ANULA;OP-0003", 66),
    ("CONSULTA;BC-0001", 35), ("CONSULTA;AD-0001", 84), ("CONSULTA;AC_0001", 14),
    ("CONSULTA;AC-1001", 21), ("CONSULTA;AC-0011", 81),
]
M, B, A = 97, 10, 94


def S(t):
    return sum(ord(c) * pow(B, len(t) - 1 - i, M) for i, c in enumerate(t)) % M


for nombre, filt in {
    "alnum": lambda s: "".join(c for c in s if c.isalnum()),
    "sin_;-_": lambda s: s.replace(";", "").replace("-", "").replace("_", ""),
}.items():
    print("==", nombre)
    for t, cc in DATOS:
        s = S(filt(t))
        print(f"{t:40} cc={cc:3} S={s:3} K=cc-A*S mod97 = {(cc - A * s) % M}")
