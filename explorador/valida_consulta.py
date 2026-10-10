"""Validacion fuera de muestra de la formula de CONSULTA.
Para cada texto nuevo: predice cc, lo envia (debe pasar el control) y envia cc+1 (debe dar E202)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402


def control_consulta(texto):
    s = "".join(c for c in texto if c.isalnum())
    h = 0
    for c in s:
        h = (h * 10 + ord(c)) % 97
    return (64 - 3 * h) % 97


TEXTOS = [
    "CONSULTA;AC-0003", "CONSULTA;AC-0010", "CONSULTA;AC-0100", "CONSULTA;AC-9999",
    "CONSULTA;AC-12345", "CONSULTA;AC-1", "CONSULTA;AC-", "CONSULTA;XYZ",
    "CONSULTA;ac-0001", "CONSULTA;AC-00a1", "CONSULTA;ZZ-0500", "CONSULTA;AB-0007",
    "CONSULTA;AC-0001-X", "CONSULTA;AC 0001", "CONSULTA;AC.0001",
    "CONSULTA;AC-0001AC-0001AC-0001", "CONSULTA;ÁC-0001", "CONSULTA;ñ",
    "CONSULTa;AC-0001", "consulta;AC-0001", "CONSULTA;A",
    "CONSULTA;" + "9" * 20, "CONSULTA;" + "A" * 40,
    "CONSULTA;AC-0050", "CONSULTA;AC-0777", "CONSULTA;QQ-1234",
]


def clasif(fila):
    r = fila["response"]
    err = r.get("error") if isinstance(r, dict) else None
    return err


def main():
    c = Cliente()
    c.reset()
    ok = 0
    for t in TEXTOS:
        cc = control_consulta(t)
        f1 = c.msg(f"{t};{cc}", "validacion", f"prediccion fuera de muestra para {t!r}: cc={cc}")
        f2 = c.msg(f"{t};{(cc + 1) % 97}", "validacion", f"contraprueba cc+1 para {t!r}")
        pasa = clasif(f1) not in ("E201", "E202")
        contra = clasif(f2) in ("E202",)
        ok += pasa
        print(f"{'OK ' if pasa else 'FALLA'} contra={'ok' if contra else 'NO'} {t!r:45} cc={cc} -> {f1['status']} {f1['response']}")
    print(f"\nPredicciones correctas: {ok}/{len(TEXTOS)}")


if __name__ == "__main__":
    main()
