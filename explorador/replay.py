"""Fase 1: reproduce los 20 ejemplos contra el original y reporta diferencias."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente, RAIZ  # noqa: E402


def main():
    c = Cliente()
    st, txt, hl = c.crudo("GET", "/health")
    print("health:", st, txt[:100])
    st, txt, hl = c.reset()
    print("reset:", st, txt[:100])
    difs = 0
    for linea in (RAIZ / "pruebas" / "ejemplos.jsonl").read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        ej = json.loads(linea)
        fila = c.msg(ej["request"]["m"], "replay1",
                     f"replay del ejemplo {ej['n']}: ¿sigue igual que en la manana?")
        igual = fila["status"] == ej["status"] and fila["response"] == ej["response"]
        if not igual:
            difs += 1
            print(f"DIFF n={ej['n']} req={ej['request']['m']}")
            print("   esperado:", ej["status"], ej["response"])
            print("   obtenido:", fila["status"], fila["response"])
    print(f"\nDiferencias: {difs}/20")


if __name__ == "__main__":
    main()
