"""Pruebas puntuales (≈12 requests): ¿0 se escribe como 97? ¿caso de 'Bna'?"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402

PRUEBAS = [
    ("ALTA;aaaba;97", "¿el control 0 mod 97 se escribe como 97?"),
    ("ALTA;aaaba;0", "¿el control 0 es aceptado como '0'?"),
    ("ALTA;aaaba;98", "¿98 y 99 aceptados como valor?"),
    ("ALTA;Ana;50", "repetir base 'Ana' (cc=50)"),
    ("ALTA;ana;50", "¿'ana' minuscula da el mismo control que 'Ana'?"),
    ("ALTA;Bna;57", "repetir 'Bna' con 57"),
    ("ALTA;bna;57", "¿'bna' minuscula acepta 57?"),
    ("ALTA;bna;41", "¿'bna' acepta el predicho 41?"),
    ("ALTA;Bna;41", "¿'Bna' acepta el predicho 41?"),
]

c = Cliente()
c.reset()
for m, h in PRUEBAS:
    f = c.msg(m, "alta_puntual", h)
    print(f"{m:18} -> {f['status']} {f['response']}")
c.reset()
