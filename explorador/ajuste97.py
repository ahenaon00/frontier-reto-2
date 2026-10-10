"""Ajuste: cc = (K + a * sum(ord(c_j) * B^idx_desde_el_final)) % M sobre texto filtrado.
Se prueba con todos los pares (texto, cc) conocidos como validos."""
import itertools

# (texto sin cc, cc) confirmados como validos (ejemplos + experimentos del 10-10)
DATOS = [
    ("ALTA;Lucia", 82), ("ALTA;Mateo", 3),
    ("CONSULTA;AC-0001", 14), ("CONSULTA;AC-0002", 11), ("CONSULTA;AC-0009", 87),
    ("DEPOSITO;AC-0001;250000", 86), ("DEPOSITO;AC-0002;700", 35),
    ("TRANSFER;AC-0001;AC-0002;40000", 86), ("TRANSFER;AC-0001;AC-0002;100000", 12),
    ("TRANSFER;AC-0001;AC-0002;120000", 55), ("TRANSFER;AC-0002;AC-0001;50000", 23),
    ("ANULA;OP-0003", 66),
    ("CONSULTA;BC-0001", 35), ("CONSULTA;AD-0001", 84), ("CONSULTA;AC_0001", 14),
    ("CONSULTA;AC-1001", 21), ("CONSULTA;AC-0011", 81), ("CONSULTA;AC-0101", 5),
]

FILTROS = {
    "alnum": lambda s: "".join(ch for ch in s if ch.isalnum()),
    "sin_sep_ni_guion": lambda s: s.replace(";", "").replace("-", "").replace("_", ""),
    "sin_;": lambda s: s.replace(";", ""),
    "todo": lambda s: s,
    "args_alnum": lambda s: "".join(ch for ch in s.split(";", 1)[1] if ch.isalnum()),
    "upper_alnum": lambda s: "".join(ch for ch in s.upper() if ch.isalnum()),
    "sin_guion_bajo_y_guion": lambda s: s.replace("-", "").replace("_", ""),
    "alnum_o_;": lambda s: "".join(ch for ch in s if ch.isalnum() or ch == ";"),
    "upper_sin_guiones": lambda s: s.upper().replace("-", "").replace("_", ""),
}


def main():
    M = 97
    for nombre, filt in FILTROS.items():
        textos = [(filt(t), cc) for t, cc in DATOS]
        for B in range(1, M):
            pot = [pow(B, k, M) for k in range(80)]
            S = [sum(ord(c) * pot[len(t) - 1 - i] for i, c in enumerate(t)) % M for t, _ in textos]
            for a in range(1, M):
                K = (textos[0][1] - a * S[0]) % M
                if all((K + a * s) % M == cc % M for s, (_, cc) in zip(S, textos)):
                    print(f"OK filtro={nombre} B={B} a={a} K={K}")
        # tambien hash 'hacia adelante' h=(h*B+ord): equivale a idx_desde_final, ya cubierto
    print("fin")


if __name__ == "__main__":
    main()
