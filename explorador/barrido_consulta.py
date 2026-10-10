"""Fase 2a (bis): barrido de control sobre CONSULTA (valida control, no muta estado).
Prepara estado: reset + ALTA;Lucia;82 (valido segun ejemplos) -> AC-0001."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402


def main():
    c = Cliente()
    c.reset()
    c.msg("ALTA;Lucia;82", "barrido_consulta", "preparar cuenta AC-0001 para barrer control")
    resumen = {}
    for n in range(100):
        cc = f"{n:02d}"
        fila = c.msg(f"CONSULTA;AC-0001;{cc}", "barrido_consulta",
                     f"¿acepta control {cc} para 'CONSULTA;AC-0001'?")
        r = fila["response"]
        clave = (fila["status"], r.get("error") if isinstance(r, dict) else str(r))
        resumen.setdefault(clave, []).append(cc)
    for k, v in resumen.items():
        print(k, v)


if __name__ == "__main__":
    main()
