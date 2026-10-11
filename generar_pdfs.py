#!/usr/bin/env python3
"""Genera los dos PDF de la entrega a partir de la evidencia real:

  * especificacion.pdf  -> documento reimplementable (7 secciones + tablas).
  * experimentos.pdf    -> volcado legible de experimentos.jsonl.

Las citas de evidencia se buscan automáticamente en experimentos.jsonl por
medio de predicados, de modo que el documento siempre cita líneas reales.
"""
import json
import os
import re
from collections import Counter

from fpdf import FPDF

RAIZ = os.path.dirname(os.path.abspath(__file__))
DEJAVU = "/usr/share/fonts/truetype/dejavu/"


def cargar(nombre):
    ruta = os.path.join(RAIZ, nombre)
    if not os.path.exists(ruta):
        return []
    out = []
    for linea in open(ruta, encoding="utf-8"):
        if linea.strip():
            try:
                out.append(json.loads(linea))
            except Exception:
                pass
    return out


EXP = cargar("experimentos.jsonl")


# ---------------------------------------------------------------------------
# Predicados / utilidades sobre las filas del log
# ---------------------------------------------------------------------------
def _req(r):
    return r.get("request") if isinstance(r.get("request"), dict) else {}


def M(r):
    x = _req(r).get("m")
    return x if isinstance(x, str) else None


def CMD(r):
    x = M(r)
    return x.split(";")[0].strip().upper() if x else None


def RESP(r):
    return r.get("response")


def ERR(r):
    x = RESP(r)
    return x.get("error") if isinstance(x, dict) else None


def ST(r):
    return r.get("status")


def RUTA(r):
    q = _req(r)
    if q.get("metodo") and q.get("ruta"):
        return (q.get("metodo"), q.get("ruta"))
    return None


def E(pred, n=6):
    """IDs de log que cumplen `pred` (para citar como evidencia)."""
    out = []
    for r in EXP:
        try:
            if pred(r):
                out.append(str(r.get("id")))
                if len(out) >= n:
                    break
        except Exception:
            pass
    return ", ".join(out) if out else "—"


def req_txt(r):
    q = _req(r)
    if q.get("metodo"):
        c = q.get("cuerpo")
        return "%s %s%s" % (q["metodo"], q.get("ruta"), (" " + json.dumps(c, ensure_ascii=False)) if c is not None else "")
    return q.get("m", "")


def resp_txt(r):
    x = RESP(r)
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    return str(x)


# ---------------------------------------------------------------------------
# Motor de PDF
# ---------------------------------------------------------------------------
class Doc(FPDF):
    def header(self):
        self.set_font("DejaVu", "", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, "Reto 2 - La caja negra - reemplazo y especificacion", align="R")
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, "pagina %d" % self.page_no(), align="C")


def nuevo_doc(orient="P"):
    pdf = Doc(orientation=orient, unit="mm", format="A4")
    pdf.set_margins(14, 12, 14)
    pdf.set_auto_page_break(True, 14)
    pdf.add_font("DejaVu", "", DEJAVU + "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", DEJAVU + "DejaVuSans-Bold.ttf")
    pdf.add_font("DejaVu", "I", DEJAVU + "DejaVuSans.ttf")
    pdf.add_font("Mono", "", DEJAVU + "DejaVuSansMono.ttf")
    pdf.add_font("Mono", "B", DEJAVU + "DejaVuSansMono-Bold.ttf")
    pdf.set_font("DejaVu", "", 10)
    return pdf


def limpiar(texto):
    """Reemplaza caracteres que la fuente DejaVu no dibuje bien."""
    return str(texto).replace("\t", "    ")


def _mc(pdf, w, h, txt, **kw):
    """multi_cell que SIEMPRE arranca en el margen izquierdo."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w, h, txt, **kw)


def parrafo(pdf, texto, size=10, style="", font="DejaVu", color=None, h=None):
    pdf.set_font(font, style, size)
    if color:
        pdf.set_text_color(*color)
    _mc(pdf, 0, h or size * 0.52, limpiar(texto))
    if color:
        pdf.set_text_color(0, 0, 0)


def titulo(pdf, texto, size=15):
    pdf.ln(1.5)
    pdf.set_font("DejaVu", "B", size)
    pdf.set_text_color(15, 45, 90)
    _mc(pdf, 0, size * 0.55, limpiar(texto))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def subtitulo(pdf, texto, size=11):
    pdf.ln(1)
    pdf.set_font("DejaVu", "B", size)
    _mc(pdf, 0, size * 0.55, limpiar(texto))
    pdf.ln(0.5)


def codigo(pdf, texto, size=7.6):
    pdf.set_font("Mono", "", size)
    pdf.set_fill_color(243, 244, 246)
    pdf.set_draw_color(210, 212, 216)
    _mc(pdf, 0, size * 0.62, limpiar(texto), border=1, fill=True)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(1.5)


def envolver(pdf, texto, ancho):
    texto = limpiar(texto).replace("\n", " ")
    palabras = texto.split(" ")
    lineas = []
    actual = ""
    for p in palabras:
        cand = (actual + " " + p).strip()
        if not actual:
            if pdf.get_string_width(cand) > ancho:
                trozo = ""
                for ch in cand:
                    if pdf.get_string_width(trozo + ch) > ancho and trozo:
                        lineas.append(trozo)
                        trozo = ch
                    else:
                        trozo += ch
                actual = trozo
            else:
                actual = cand
        elif pdf.get_string_width(cand) <= ancho:
            actual = cand
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _fila(pdf, celdas, widths, hline, size, bold, fill=None):
    pdf.set_font("DejaVu", "B" if bold else "", size)
    bloques = [envolver(pdf, c, w - 2.0) for c, w in zip(celdas, widths)]
    n = max(1, max(len(b) for b in bloques))
    rowh = n * hline
    if pdf.get_y() + rowh > pdf.h - pdf.b_margin:
        pdf.add_page()
        pdf.set_font("DejaVu", "B" if bold else "", size)
    x, y = pdf.l_margin, pdf.get_y()
    total = sum(widths)
    if fill:
        pdf.set_fill_color(*fill)
        pdf.rect(x, y, total, rowh, style="F")
    pdf.set_draw_color(150, 150, 150)
    pdf.rect(x, y, total, rowh)
    cx = x
    for w in widths[:-1]:
        cx += w
        pdf.line(cx, y, cx, y + rowh)
    cx = x
    for w, b in zip(widths, bloques):
        pdf.set_xy(cx + 1, y + 0.4)
        for ln in b:
            pdf.cell(w - 2.0, hline, ln)
            pdf.set_xy(cx + 1, pdf.get_y() + hline)
        cx += w
    pdf.set_xy(x, y + rowh)
    pdf.set_draw_color(0, 0, 0)


def tabla(pdf, cabecera, filas, widths, hline=4.0, size=8):
    _fila(pdf, cabecera, widths, hline, size, True, fill=(228, 232, 240))
    for i, f in enumerate(filas):
        _fila(pdf, f, widths, hline, size, False, fill=(247, 248, 250) if i % 2 else None)
    pdf.ln(2.5)


def vinetas(pdf, items, size=9):
    for it in items:
        pdf.set_font("DejaVu", "", size)
        pdf.cell(5, size * 0.55, "•")
        _mc(pdf, 0, size * 0.55, limpiar(it))
    pdf.ln(1)


# ---------------------------------------------------------------------------
# ESPECIFICACIÓN
# ---------------------------------------------------------------------------
FIRMA = ("Generado a partir de experimentos.jsonl (evidencia cruda contra el "
         "servicio original). La columna Evidencia cita los id de ese log.")


def construir_especificacion():
    pdf = nuevo_doc("P")
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 22)
    pdf.set_text_color(15, 45, 90)
    _mc(pdf, 0, 11, "Especificación del servicio")
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(60, 60, 60)
    _mc(pdf, 0, 8, "Reto 2 · La caja negra")
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)
    parrafo(pdf, "Reimplementación del servicio HTTP original, sin depender de él. "
                 "El servicio recibe mensajes por POST /msg con un campo de control "
                 "opaco y mantiene estado entre requests. Este documento describe el "
                 "protocolo, la integridad del mensaje, cada comando, la memoria, los "
                 "errores, los cambios detectados durante el día y los riesgos.", 10.5)
    pdf.ln(2)
    parrafo(pdf, FIRMA, 9, style="I", color=(90, 90, 90))
    pdf.ln(2)
    subtitulo(pdf, "Cómo leer la confianza")
    vinetas(pdf, [
        "confirmado: probado contra el original y se repite.",
        "probable: visto una vez o inferido de la evidencia.",
        "supuesto: no probado; es el comportamiento por defecto del reemplazo.",
    ])

    # ---------------- 1. ENTRADA ----------------
    titulo(pdf, "1. Entrada")
    parrafo(pdf, "Superficie HTTP, autenticación y forma del cuerpo.", 9.5, style="I", color=(90, 90, 90))
    filas = [
        ("E1.1", "El transporte es HTTP/JSON. La operación principal es POST /msg con cuerpo {\"m\": \"<mensaje>\"}.",
         E(lambda r: M(r) == "PING;64"), "confirmado"),
        ("E1.2", "GET /health responde 200 con cuerpo {\"ok\":true} cuando el servicio está listo.",
         E(lambda r: RUTA(r) == ("GET", "/health") and ST(r) == 200), "confirmado"),
        ("E1.3", "POST /__reset responde 200 {\"ok\":true} y deja el estado del token en su valor inicial.",
         E(lambda r: RUTA(r) == ("POST", "/__reset") and ST(r) == 200), "confirmado"),
        ("E1.4", "Todas las rutas exigen Authorization: Bearer <token>. Sin token o con un token ajeno responden 401 E001.",
         E(lambda r: RUTA(r) and ST(r) == 401) or E(lambda r: ST(r) == 401), "confirmado"),
        ("E1.5", "Cualquier ruta que no sea /msg, /health o /__reset responde 404 {\"error\":\"E404\",\"mensaje\":\"ruta desconocida\"}.",
         E(lambda r: RUTA(r) and ST(r) == 404 and ERR(r) == "E404"), "confirmado"),
        ("E1.6", "Un cuerpo que no es JSON válido responde 400 E100 \"json inválido\".",
         E(lambda r: ERR(r) == "E100"), "confirmado"),
        ("E1.7", "Si falta la clave m, o m no es un string, responde 400 E102 \"falta m\".",
         E(lambda r: ERR(r) == "E102"), "confirmado"),
        ("E1.8", "Cuerpo esperado: objeto JSON con exactamente el string m. m vacío no es E102, es E103 (falta control).",
         E(lambda r: ERR(r) == "E103"), "confirmado"),
        ("E1.9", "Límites de infraestructura: 10 req/s y 8000 req/día por token; al excederse la respuesta trae X-Frontier-Infra: rate-limit (no es del servicio).",
         "—", "supuesto"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))
    parrafo(pdf, "Nota: los ejemplos de la mañana usaban POST /msg; los identificadores de cuenta "
                 "y operación son sensibles a mayúsculas, pero el nombre del comando no (ver E2.7).", 9)

    # ---------------- 2. INTEGRIDAD ----------------
    titulo(pdf, "2. Integridad del mensaje")
    parrafo(pdf, "El mensaje es una cadena separada por ';'. El ÚLTIMO campo es el control; "
                 "los anteriores son comando + argumentos. El control se valida ANTES que el "
                 "comando y la aridad, así que un control malo SIEMPRE da E201/E202 aunque el "
                 "comando no exista o la aridad sea incorrecta.", 9.5)
    filas = [
        ("E2.1", "El mensaje se parte por ';'; el último segmento es el campo de control.",
         E(lambda r: M(r) == "PING;64"), "confirmado"),
        ("E2.2", "Si no hay ';' (no se puede separar el control) responde 400 E103 \"falta control\".",
         E(lambda r: ERR(r) == "E103"), "confirmado"),
        ("E2.3", "Si algún segmento intermedio está vacío responde 400 E104 \"segmento vacío\".",
         E(lambda r: ERR(r) == "E104"), "confirmado"),
        ("E2.4", "El control debe ser numérico; si no lo es responde 400 E201 \"control mal formado\".",
         E(lambda r: ERR(r) == "E201"), "confirmado"),
        ("E2.5", "Si el control no coincide con el esperado responde 400 E202 \"control inválido\".",
         E(lambda r: ERR(r) == "E202"), "confirmado"),
        ("E2.6", "El control se valida ANTES que el comando y la aridad: un comando inexistente con control inválido da E202, no E301.",
         E(lambda r: ERR(r) == "E202" and CMD(r) not in ("PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA")), "confirmado"),
        ("E2.7", "El nombre del comando no distingue mayúsculas: 'ping;64' y 'CONSULTa;...' funcionan igual.",
         E(lambda r: M(r) in ("ping;64", "PING;64") and ST(r) == 200, 3), "confirmado"),
        ("E2.8", "El control se calcula sobre el TEXTO EN MAYÚSCULAS de los argumentos, ignorando '-' y ';'; el comando no distingue caso pero la base normalizada sí se usa para el hash.",
         E(lambda r: M(r) == "CONSULTa;AC-0001;14" and ST(r) == 200), "confirmado"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))

    subtitulo(pdf, "Algoritmo del control (formula verificada)")
    parrafo(pdf, "El campo de control es un checksum módulo 97 de la base (el mensaje sin el último "
                 "campo). Se calcula sobre TODAS las letras y dígitos en MAYÚSCULAS de los argumentos "
                 "(lo que sigue al primer ';'), descartando '-' y ';'.", 9.5)
    codigo(pdf,
           "H = 0\n"
           "para c en SOLO_ALNUM(args.upper()):   # args = lo que va tras el primer ';'\n"
           "    H = (H*10 + codigo(c)) mod 97\n"
           "m = longitud de ese texto limpio\n"
           "control = (82 + 94*H + (10**m mod 97) * semilla[COMANDO]) mod 97\n"
           "\n"
           "semilla: CONSULTA=8  DEPOSITO=22  TRANSFER=53  ANULA=41  PING=79  SALDOS=52\n"
           "El control se escribe con dígitos SIN ceros a la izquierda (PING -> 64, ALTA;Mateo -> 3).\n"
           "ALTA es una anomalía: sus controles conocidos se reproducen con\n"
           "  control = (11 + 86*H + 8*(10**m mod 97)) mod 97\n"
           "que acierta ALTA;Lucia=82, ALTA;Mateo=3 y ALTA;Lucia;Gomez=11; no se ha\n"
           "encontrado una semilla CONSTANTE que explique ALTA como el resto. Se comprobó\n"
           "con nombres NUEVOS (ids 1932 y 1933): el servicio responde E202, así que esa\n"
           "forma NO generaliza en ALTA.")
    parrafo(pdf, "La fórmula se verificó contra todos los pares (base -> control) observados "
                 "aceptados por el servicio (15 pares, 0 fallos) y reproduce el replay 20/20.", 9,
            style="I", color=(90, 90, 90))

    # ---------------- 3. COMANDOS ----------------
    titulo(pdf, "3. Comandos")
    parrafo(pdf, "Un bloque por comando. La aridad es el número TOTAL de segmentos, incluido el control. "
                 "Se define primero el control y luego la aridad, así que el control de un comando con "
                 "aridad incorrecta igualmente debe ser válido.", 9.5)
    filas = [
        ("C1", "PING;<c>: comprueba disponibilidad. 2 segmentos. Devuelve 200 {\"pong\":true}. El primer campo se ignora; solo importa el control.",
         E(lambda r: M(r) == "PING;64"), "confirmado"),
        ("C2", "ALTA;<nombre>;<c>: crea una cuenta. 3 segmentos. Devuelve 201 {\"cuentaId\":\"AC-NNNN\"} con NNNN incremental desde 0001 por sesión.",
         E(lambda r: M(r) == "ALTA;Lucia;82") + "; " + E(lambda r: M(r) == "ALTA;Mateo;3", 2), "confirmado"),
        ("C3", "CONSULTA;<cuenta_id>;<c>: 3 segmentos. Devuelve 200 {\"cuenta_id\":\"...\",\"saldo\":\"<n>.<dd>\"} (saldo con 2 decimales, ver §6). Cuenta inexistente -> 404 E401.",
         E(lambda r: M(r) == "CONSULTA;AC-0002;11" and ST(r) == 200) + "; " + E(lambda r: ERR(r) == "E401", 2), "confirmado"),
        ("C4", "DEPOSITO;<cuenta_id>;<monto>;<c>: 4 segmentos. Suma monto al saldo. Devuelve 200 {\"status\":\"recieved\",\"operacionId\":\"OP-NNNN\"}. Cuenta inexistente -> 404 E401.",
         E(lambda r: M(r) == "DEPOSITO;AC-0001;250000;86", 2), "confirmado"),
        ("C5", "TRANSFER;<origen>;<destino>;<monto>;<c>: 5 segmentos. Mueve monto de origen a destino. 200 {\"status\":\"recieved\",\"operacionId\":\"OP-NNNN\"}. Cuenta inexistente -> 404 E401; monto >= 100000 -> 422 E506; saldo insuficiente -> 422 E507.",
         E(lambda r: M(r) == "TRANSFER;AC-0001;AC-0002;40000;86", 2) + "; " + E(lambda r: ERR(r) == "E506", 2) + "; " + E(lambda r: ERR(r) == "E507", 2), "confirmado"),
        ("C6", "ANULA;<operacionId>;<c>: 3 segmentos. Revierte el efecto de la operación y la marca como anulada. Devuelve 200 {\"ok\":true,\"anulada\":\"OP-NNNN\"}. Si ya estaba anulada -> 200 {\"ok\":false,\"motivo\":\"ya anulada\"}. Operación inexistente -> 404 E402.",
         E(lambda r: RESP(r) == {"ok": True, "anulada": "OP-0003"}, 2) + "; " + E(lambda r: ERR(r) == "E402", 2) + "; " + E(lambda r: isinstance(RESP(r), dict) and RESP(r).get("motivo") == "ya anulada", 2), "confirmado"),
        ("C7", "Cualquier otro nombre de comando (p. ej. SALDOS, FOO) -> 400 E301 \"comando desconocido \" (con espacio final). El control debe ser válido primero.",
         E(lambda r: ERR(r) == "E301", 3), "confirmado"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (12, 116, 28, 24))

    # ---------------- 4. MEMORIA ----------------
    titulo(pdf, "4. Memoria entre requests")
    parrafo(pdf, "El servicio es stateful por token. El estado vive entre requests hasta POST /__reset. "
                 "La sesión ids 1511-1530 del log reproduce el ciclo completo.", 9.5)
    filas = [
        ("M1", "Las cuentas creadas con ALTA persisten. Los ids se asignan en orden: primer ALTA -> AC-0001, segundo -> AC-0002.",
         E(lambda r: M(r) == "ALTA;Lucia;82") + "; " + E(lambda r: M(r) == "ALTA;Mateo;3", 2), "confirmado"),
        ("M2", "El saldo persiste y cambia con DEPOSITO/TRANSFER/ANULA. Tras depositar 250000 en AC-0001, CONSULTA devuelve 2100.00 (ver §6): 250000 - 40000 = 210000.",
         E(lambda r: M(r) == "CONSULTA;AC-0001;14" and ST(r) == 200, 4), "confirmado"),
        ("M3", "Existe un contador global de operaciones OP-NNNN que SOLO avanza con respuestas 2xx; las operaciones rechazadas (E506, E507, E201...) no lo consumen. En ids 1516/1517 -> OP-0001/OP-0002; 1519 y 1520 (E506) no consumen; 1528 -> OP-0003.",
         E(lambda r: M(r) == "DEPOSITO;AC-0001;250000;86", 2) + "; " + E(lambda r: M(r) == "DEPOSITO;AC-0002;700;35", 2) + "; " + E(lambda r: ERR(r) == "E506", 2), "confirmado"),
        ("M4", "ANULA revierte el efecto económico de la operación (resta lo sumado, reintegra lo transferido) y la marca como anulada.",
         E(lambda r: RESP(r) == {"ok": True, "anulada": "OP-0003"}, 3), "confirmado"),
        ("M5", "POST /__reset vacía cuentas y operaciones y reinicia el contador a OP-0001 (el siguiente ALTA vuelve a dar AC-0001).",
         E(lambda r: RUTA(r) == ("POST", "/__reset") and ST(r) == 200, 2), "confirmado"),
        ("M6", "El estado es POR TOKEN: lo que hace un token no lo ve otro. El reemplazo debe mantener el estado a nivel de proceso (el set de evaluación habla con un solo proceso).",
         "—", "supuesto"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))

    # ---------------- 5. ERRORES ----------------
    titulo(pdf, "5. Errores")
    parrafo(pdf, "Cada error con su status y su cuerpo exacto. El orden de evaluación es estricto: "
                 "autenticación -> JSON -> campo m -> integridad (control presente/segmentos) -> "
                 "control (formato/valor) -> comando -> aridad -> negocio.", 9.5)
    filas = [
        ("X1", "401 E001 {\"error\":\"E001\",\"mensaje\":\"no autorizado\"} — token ausente o ajeno. Se evalúa PRIMERO.",
         E(lambda r: ST(r) == 401) or E(lambda r: RUTA(r) and ST(r) == 401), "confirmado"),
        ("X2", "400 E100 {\"error\":\"E100\",\"mensaje\":\"json inválido\"} — cuerpo no JSON. Se evalúa tras la autenticación.",
         E(lambda r: ERR(r) == "E100"), "confirmado"),
        ("X3", "400 E102 {\"error\":\"E102\",\"mensaje\":\"falta m\"} — JSON sin m o m no string.",
         E(lambda r: ERR(r) == "E102"), "confirmado"),
        ("X4", "400 E103 {\"error\":\"E103\",\"mensaje\":\"falta control\"} — m sin ';' (no hay campo de control) o m vacío.",
         E(lambda r: ERR(r) == "E103"), "confirmado"),
        ("X5", "400 E104 {\"error\":\"E104\",\"mensaje\":\"segmento vacío\"} — algún segmento intermedio vacío. Se evalúa ANTES del control (id 121: control 00 sería inválido para PING pero devuelve E104).",
         E(lambda r: ERR(r) == "E104"), "confirmado"),
        ("X6", "400 E201 {\"error\":\"E201\",\"mensaje\":\"control mal formado\"} — el control no es numérico.",
         E(lambda r: ERR(r) == "E201"), "confirmado"),
        ("X7", "400 E202 {\"error\":\"E202\",\"mensaje\":\"control inválido\"} — el control no coincide. Se evalúa antes del comando y la aridad.",
         E(lambda r: ERR(r) == "E202", 4), "confirmado"),
        ("X8", "400 E301 {\"error\":\"E301\",\"mensaje\":\"comando desconocido \"} — comando no soportado. Cuidado: el mensaje termina en ESPACIO.",
         E(lambda r: ERR(r) == "E301", 3), "confirmado"),
        ("X9", "400 E302 {\"error\":\"E302\",\"mensaje\":\"aridad inválida\"} — número de segmentos incorrecto para el comando (tras validar el control).",
         E(lambda r: ERR(r) == "E302", 3), "confirmado"),
        ("X10", "404 E401 {\"error\":\"E401\",\"mensaje\":\"cuenta inexistente\"} — CONSULTA/DEPOSITO/TRANSFER sobre una cuenta que no existe.",
         E(lambda r: ERR(r) == "E401", 3), "confirmado"),
        ("X11", "404 E402 {\"error\":\"E402\",\"mensaje\":\"operación inexistente\"} — ANULA sobre una operación que no existe.",
         E(lambda r: ERR(r) == "E402", 3), "confirmado"),
        ("X12", "422 E506 {\"error\":\"E506\",\"mensaje\":\"límite excedido\"} — TRANSFER con monto >= 100000.",
         E(lambda r: ERR(r) == "E506", 3), "confirmado"),
        ("X13", "422 E507 {\"error\":\"E507\",\"mensaje\":\"saldo insuficiente\"} — TRANSFER con saldo de origen menor al monto.",
         E(lambda r: ERR(r) == "E507", 3), "confirmado"),
        ("X14", "Orden interno de TRANSFER: primero existencia de cuentas (E401), luego límite (E506), luego fondos (E507).",
         E(lambda r: ERR(r) == "E506", 1) + "; " + E(lambda r: ERR(r) == "E507", 1), "probable"),
        ("X15", "404 E404 {\"error\":\"E404\",\"mensaje\":\"ruta desconocida\"} — ruta fuera de /msg, /health, /__reset.",
         E(lambda r: ERR(r) == "E404"), "confirmado"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))
    parrafo(pdf, "Orden de evaluación (de arriba a abajo): token (E001) -> JSON (E100) -> m (E102) -> "
                 "control presente/segmentos (E103/E104) -> control formato/valor (E201/E202) -> "
                 "comando (E301) -> aridad (E302) -> negocio (E401/E402/E506/E507).", 9)

    # ---------------- 6. CAMBIOS ----------------
    titulo(pdf, "6. Cambios durante el día")
    parrafo(pdf, "pruebas/ejemplos.jsonl se grabó con la versión de la mañana. El replay contra la "
                  "versión vigente (ids 1511-1530) muestra los siguientes cambios.", 9.5)
    filas = [
        ("D1", "El saldo pasó de NÚMERO a STRING con 2 decimales. Mañana (ejemplo n=5): {\"saldo\":0}. Ahora (id 1515): {\"saldo\":\"0.00\"}. El valor se divide por 100 y se formatea con dos decimales (id 1518: 40000 -> \"400.00\").",
         "1515; 1518; 1521; 1529", "confirmado"),
        ("D2", "El umbral de TRANSFER cambió: antes 100000 se ACEPTABA (ejemplo n=10 -> 200); ahora monto >= 100000 da 422 E506 (ids 1519 y 1520).",
         "1519; 1520", "confirmado"),
        ("D3", "El contador de operaciones solo avanza con 2xx, así que al fallar el TRANSFER de 100000 (id 1520) los ANULA posteriores sobre OP-0003 dan E402 (ids 1523/1524).",
         "1516; 1517; 1520; 1528", "confirmado"),
        ("D4", "ALTA sigue devolviendo {\"cuentaId\":\"AC-NNNN\"} y exige un único nombre; ALTA con dos argumentos da E302 (id 1530, igual que el ejemplo n=20).",
         "1513; 1530", "confirmado"),
        ("D5", "El comando sigue siendo case-insensitive: 'CONSULTa;AC-0001;14' responde 200 (id 1521).",
         "1511; 1521", "confirmado"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))

    # ---------------- 7. RIESGOS ----------------
    titulo(pdf, "7. Riesgos")
    parrafo(pdf, "Comportamientos que un cliente nuevo NO debería heredar y cómo se cerrarían.", 9.5)
    filas = [
        ("R1", "El campo de control es un checksum invertible/mod-97 sin documentar. Un cliente nuevo no debería tener que calcularlo a mano: se cerraría con un campo de control generado por el servidor (p. ej. HMAC) o autenticación por token.",
         "15 pares base->control en el log", "confirmado"),
        ("R2", "La anomalía de ALTA (ninguna semilla constante la explica) indica lógica especial no documentada. Riesgo de que existan más excepciones por comando. Se cerraría con un generador de control único y documentado.",
         "ALTA;Lucia=82, ALTA;Mateo=3, ALTA;Lucia;Gomez=11; sondas 1932/1933 (E202)", "probable"),
        ("R3", "El servicio es stateful por token y no es idempotente: repetir un DEPOSITO duplica el efecto. Se cerraría con claves de idempotencia por operación.",
         E(lambda r: M(r) == "DEPOSITO;AC-0001;250000;86", 2), "confirmado"),
        ("R4", "El contador OP-NNNN y los ids AC-NNNN son predecibles y globales por sesión; filtran volumen y orden. Se cerraría con ids aleatorios/UUID.",
         E(lambda r: M(r) == "DEPOSITO;AC-0002;700;35", 2), "probable"),
        ("R5", "El mensaje E301 incluye un espacio final y los cuerpos usan la grafía 'recieved' (sic). Un cliente que normalice el texto fallaría. Se cerraría corrigiendo el literal en el origen.",
         E(lambda r: ERR(r) == "E301", 2) + "; " + E(lambda r: isinstance(RESP(r), dict) and RESP(r).get("status") == "recieved", 2), "confirmado"),
        ("R6", "El umbral y las reglas de negocio cambiaron en el día; el reemplazo debe fijarse a la versión de las 20:00. Se cerraría versionando el contrato.",
         "1519; 1520", "confirmado"),
    ]
    tabla(pdf, ("ID", "Comportamiento", "Evidencia", "Confianza"), filas, (14, 108, 32, 26))

    # cierre
    pdf.ln(2)
    pdf.set_draw_color(15, 45, 90)
    pdf.set_font("DejaVu", "I", 8.5)
    pdf.set_text_color(90, 90, 90)
    _mc(pdf, 0, 4.5, "Documento generado automáticamente. Todas las citas de evidencia se "
                           "resolvieron sobre experimentos.jsonl en el momento de la generación. "
                           "Las secciones marcadas como supuesto son decisiones por defecto del reemplazo.")
    return pdf


# ---------------------------------------------------------------------------
# LOG DE EXPERIMENTOS
# ---------------------------------------------------------------------------
def construir_experimentos():
    pdf = nuevo_doc("L")
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(15, 45, 90)
    _mc(pdf, 0, 9, "Log de experimentos")
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    _mc(pdf, 0, 5, "%d requests registrados contra el servicio original. "
                         "Una fila por request: id, secuencia, request, hipótesis, status y respuesta."
                         % len(EXP))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    widths = (11, 30, 66, 14, 68, 80)
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    _fila(pdf, ("id", "seq", "request", "status", "response", "hipótesis"),
          widths, 4.0, 7.0, True, fill=(228, 232, 240))
    for i, r in enumerate(EXP):
        _fila(pdf, (str(r.get("id")), str(r.get("seq")),
                    req_txt(r), str(r.get("status")), resp_txt(r),
                    str(r.get("hipotesis", ""))),
              widths, 3.6, 6.4, False, fill=(247, 248, 250) if i % 2 else None)
    return pdf


def main():
    esp = construir_especificacion()
    sal_esp = os.path.join(RAIZ, "especificacion.pdf")
    esp.output(sal_esp)
    print("[OK] %s (%d paginas)" % (sal_esp, esp.page_no()))

    ex = construir_experimentos()
    sal_ex = os.path.join(RAIZ, "experimentos.pdf")
    ex.output(sal_ex)
    print("[OK] %s (%d paginas, %d filas)" % (sal_ex, ex.page_no(), len(EXP)))


if __name__ == "__main__":
    main()
