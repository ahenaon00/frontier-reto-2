from pypdf import PdfReader

r = PdfReader("especificacion.pdf")
todo = "\n".join((p.extract_text() or "") for p in r.pages)
for clave in ["E2.6", "E2.5", "E2.7", "C5", "X14", "R2", "D2"]:
    idx = todo.find(clave)
    print("---", clave, "---")
    print(todo[idx:idx + 220].replace("\n", " ") if idx >= 0 else "NO ENCONTRADO")
    print()
