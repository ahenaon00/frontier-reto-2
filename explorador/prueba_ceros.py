"""Prueba puntual: ¿el control se compara como string sin relleno de ceros? (5 vs 05)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402

c = Cliente()
c.reset()
for m, h in [
    ("CONSULTA;AC-0101;5", "prediccion mod97 da 5: ¿acepta sin cero a la izquierda?"),
    ("CONSULTA;AC-0101;05", "¿rechaza el mismo valor con cero a la izquierda?"),
    ("CONSULTA;AC-0101;005", "¿acepta tres digitos con ceros?"),
    ("CONSULTA;AC-0101;+5", "¿acepta signo +?"),
    ("CONSULTA;AC-0101;5.0", "¿acepta decimal?"),
    ("CONSULTA;AC-0101; 5", "¿acepta espacio?"),
    ("CONSULTA;AC-0101;-5", "¿acepta signo -?"),
]:
    f = c.msg(m, "ceros", h)
    print(m, f["status"], f["response"])
