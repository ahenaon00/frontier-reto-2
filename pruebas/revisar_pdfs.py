from pypdf import PdfReader
import sys

for nombre in ["especificacion.pdf", "experimentos.pdf"]:
    r = PdfReader(nombre)
    print("==== %s : %d paginas ====" % (nombre, len(r.pages)))
    for i in range(min(2, len(r.pages))):
        txt = r.pages[i].extract_text() or ""
        print("--- pagina %d ---" % (i + 1))
        print(txt[:2600])
    print()
