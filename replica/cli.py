import argparse
import requests
import motor_hash
import sys

URL_REPLICA = "http://localhost:8000/procesar"

def main():
    parser = argparse.ArgumentParser(description="CLI para interactuar con la Réplica de la Caja Negra local")
    parser.add_argument("comando", help="Comando a enviar (ej. CONSULTA, DEPOSITO)")
    parser.add_argument("argumentos", nargs="?", default="", help="Argumentos del comando (ej. juan_perez)")
    parser.add_argument("--control", help="Dígito de control explícito (Si se omite, se autocalcula con el motor)")
    
    args = parser.parse_args()
    
    # Autocompletar el control si el usuario no lo forzó manualmente
    control = args.control
    if not control:
        control = motor_hash.calcular_digito_control(args.comando, args.argumentos)
        print(f"[*] Control autocalculado: {control}")
        
    payload = {
        "comando": args.comando,
        "argumentos": args.argumentos,
        "control": control
    }
    
    print(f"[*] Enviando a Réplica Local: {payload}")
    
    try:
        resp = requests.post(URL_REPLICA, json=payload)
        if resp.status_code == 200:
            print(f"\n[+] ÉXITO (200): {resp.json()}")
        else:
            print(f"\n[-] ERROR ({resp.status_code}): {resp.json()}")
    except requests.exceptions.ConnectionError:
        print("\n[!] ERROR FATAL: No se pudo conectar a la réplica.")
        print("[!] Solución: Abre otra terminal y ejecuta 'uvicorn servidor:app --reload' dentro de la carpeta replica/")
        sys.exit(1)

if __name__ == "__main__":
    main()
