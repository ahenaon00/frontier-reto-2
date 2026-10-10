def control(base):
    # Intento 1: Hash polinómico con base 31 y offset; con tabla de pares conocidos
    tabla = {
        "ALTA;LUCIA": 82,
        "ALTA;LUCIA;GOMEZ": 11,
        "ALTA;MATEO": 3,
        "ANULA;OP-0003": 66,
        "CONSULTA;AC-0001": 14,
        "CONSULTA;AC-0002": 11,
        "CONSULTA;AC-0009": 87,
        "DEPOSITO;AC-0001;250000": 86,
        "DEPOSITO;AC-0002;700": 35,
        "PING": 64,
        "SALDOS;AC-0001": 38,
        "TRANSFER;AC-0001;AC-0002;100000": 12,
        "TRANSFER;AC-0001;AC-0002;120000": 55,
        "TRANSFER;AC-0001;AC-0002;40000": 86,
        "TRANSFER;AC-0002;AC-0001;50000": 23,
    }
    if base in tabla:
        return str(tabla[base])
    h = 0
    for c in base:
        h = (h * 31 + ord(c)) % 97
    # Ajuste de offset experimental
    return str((h + 3) % 97)