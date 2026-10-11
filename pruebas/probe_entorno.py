import importlib, shutil, os

for m in ["reportlab", "fpdf", "weasyprint", "markdown", "xhtml2pdf", "fpdf2", "PIL"]:
    try:
        mod = importlib.import_module(m)
        print("OK  ", m, getattr(mod, "__version__", ""))
    except Exception as e:
        print("NO  ", m, type(e).__name__)

print("--- binarios ---")
for b in ["soffice", "libreoffice", "pandoc", "wkhtmltopdf", "chromium", "chromium-browser", "google-chrome"]:
    print(b, "->", shutil.which(b))

print("--- fuentes ---")
for d in ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype", "/mnt/c/Windows/Fonts"]:
    print(d, "->", os.path.isdir(d), os.listdir(d)[:8] if os.path.isdir(d) else "")
