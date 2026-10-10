import re

SEMILLAS = {
    "CONSULTA": 8,
    "DEPOSITO": 22,
    "TRANSFER": 53,
    "ANULA": 41,
    "ALTA": 0 # Anomalía por descubrir
}

def calcular_hash_horner(texto: str) -> tuple[int, int]:
    """
    Calcula el hash de Horner base 10 módulo 97 sobre los caracteres
    alfanuméricos, e ignora separadores. Retorna el hash y la longitud (m).
    """
    limpio = re.sub(r'[^a-zA-Z0-9]', '', texto).lower()
    h = 0
    for char in limpio:
        h = (h * 10 + ord(char)) % 97
    return h, len(limpio)

def calcular_digito_control(comando: str, argumentos: str) -> str:
    comando = comando.upper()
    if comando == "PING":
        return "00" # PING ignora el control matemáticamente
        
    semilla = SEMILLAS.get(comando, 0)
    h, m = calcular_hash_horner(argumentos)
    
    # Ecuación polinomial: cc = (82 + 94 * H(args) + 10^m * s_cmd) mod 97
    cc = (82 + 94 * h + (10**m) * semilla) % 97
    
    # 0 se representa como 97
    if cc == 0:
        cc = 97
        
    return f"{cc:02d}"
