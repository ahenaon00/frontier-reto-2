def solve():
    payloads = [
        ("PING", 64),
        ("ALTA;Lucia", 82),
        ("ALTA;Mateo", 3),
        ("CONSULTA;AC-0001", 14),
        ("DEPOSITO;AC-0001;250000", 86),
        ("TRANSFER;AC-0001;AC-0002;40000", 86),
        ("CONSULTA;AC-0002", 11),
        ("TRANSFER;AC-0001;AC-0002;100000", 12),
        ("CONSULTa;AC-0001", 14),
        ("ANULA;OP-0003", 66),
        ("DEPOSITO;AC-0002;700", 35),
    ]

    def check(transform, M):
        for A in range(1, 100):
            for B in range(0, 100):
                ok = True
                for base, control in payloads:
                    val = sum(ord(c) for c in transform(base))
                    if (val * A + B) % M != control:
                        ok = False
                        break
                if ok:
                    print(f"FOUND: A={A}, B={B}, M={M} with {transform.__name__}")
                    return True
        return False

    print("Checking upper, M=97")
    check(lambda x: x.upper(), 97)
    print("Checking lower, M=97")
    check(lambda x: x.lower(), 97)
    print("Checking exact, M=97")
    check(lambda x: x, 97)

solve()
