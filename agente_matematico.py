"""Agente científico para la caja negra (ciclo dirigido por el MODELO).

FILOSOFÍA DE ESTE PROGRAMA
==========================
El cerebro es el modelo de OpenRouter. El programa NO intenta adivinar la
fórmula: solo

  1. RECOLECTA evidencia real del servicio (replay de los ejemplos + los
     experimentos que pide el modelo) y la guarda en `patrones_encontrados.jsonl`;
  2. se la ENTREGA al modelo junto con el resultado de sus predicciones;
  3. EJECUTA contra el servicio real los experimentos NUEVOS que el modelo
     propone, y le devuelve si acertó o falló.

El modelo decide el siguiente paso:
  - si sus predicciones encajan con el patrón que propuso, sigue probando
    dentro de ese patrón (lo extiende a casos nuevos para confirmarlo);
  - si fallan, revisa el patrón con los datos frescos y propone experimentos
    que distingan entre sus hipótesis, hasta tener datos suficientes para
    encontrar el patrón y empezar a predecir directamente.

Novedades de esta versión
=========================
- RÁPIDO Y DENSO: modelo por defecto o3-mini con razonamiento "low" y sin
  cadena de razonamiento en la respuesta; hasta 15 experimentos y de 1 a 3
  candidatas de control por ronda (el laboratorio las evalúa todas gratis).
- METODOLOGÍA POR GRUPOS: la evidencia agrupa los payloads por resultado
  (200/201/400 E202/404 E401...) para que el modelo busque qué tienen en común,
  replique primero los grupos conocidos y deje los demás para después.
- PISTAS ARITMÉTICAS automáticas: detecta progresiones entre bases que solo
  cambian en el número final y, si hay envoltura, el MÓDULO que las explica
  (p. ej. mod 97). Empuja al checksum lineal y NO al CRC.
- LABORATORIO DE CONTROL: evalúa `control(base)` GRATIS (0 requests) contra
  todos los pares (base -> control) ya observados y devuelve los fallos.
- MARCADOR '?' (prueba de GENERALIZACIÓN): el modelo termina un payload en ';?'
  y el programa lo sustituye por lo que devuelve su propia `control(base)`. Así
  se comprueba si la fórmula generaliza a bases NUEVAS (E202 = falló; otro
  resultado = acertó) sin que el modelo tenga que calcular el valor a mano ni
  escribir expresiones en el JSON. Evita que una TABLA memorizada parezca
  resuelta (el lab no distingue memorizar de generalizar).
- FEEDBACK CLASIFICADO + COBERTURA POR GRUPO: cada respuesta se etiqueta por
  causa y la réplica informa qué grupos ya reproduce y cuáles faltan.
- PRE-VALIDACIÓN: los payloads con control no numérico y sin candidata `control`
  se descartan SIN gastar request.
- No se repiten payloads ya probados (normalizado, case-insensitive).
- REINICIAR=1 arranca con evidencia limpia (guarda copia .bak). REPETIR=1
  permite forzar la repetición de payloads. ESFUERZO=low|medium|high|none.

Se conservan los prints de prueba a lo largo de todo el proceso.
"""

import io
import json
import os
import re
import sys
import time

import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from explorador.cliente import Cliente

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
RAIZ = os.path.dirname(os.path.abspath(__file__))


def _leer_env():
    """Lee el .env del proyecto (sin pisar el entorno del sistema)."""
    env = {}
    ruta = os.path.join(RAIZ, ".env")
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                if "=" in linea and not linea.strip().startswith("#"):
                    k, v = linea.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


_ENV = _leer_env()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or _ENV.get("OPENROUTER_API_KEY")
# Modelo de razonamiento por defecto (o3-mini: bastante más rápido que o3).
# Alternativas: "openai/o3", "deepseek/deepseek-r1:free".
MODELO = os.environ.get("MODELO") or _ENV.get("MODELO") or "openai/o3-mini"

RUTA_DATASET = os.path.join(RAIZ, "pruebas", "ejemplos.jsonl")
PATRONES_JSONL = os.path.join(RAIZ, "patrones_encontrados.jsonl")
EJEMPLOS_NUEVOS = os.path.join(RAIZ, "pruebas", "ejemplos_nuevos.jsonl")

# Cuántos ciclos (llamadas al modelo) como máximo.
MAX_RONDAS = int(os.environ.get("LLM_RONDAS", "15"))
# Tope TOTAL de requests al servicio real durante toda la corrida.
PRESUPUESTO_TOTAL = int(os.environ.get("PRESUPUESTO", "150"))
# Tope de experimentos por ronda: denso (la dedup y el presupuesto protegen).
MAX_EXPERIMENTOS_RONDA = int(os.environ.get("MAX_EXPERIMENTOS", "15"))
# Esfuerzo de razonamiento para modelos o-series (low/medium/high). "low" acelera.
ESFUERZO = os.environ.get("ESFUERZO", "low")
# Si REPETIR=1, permite re-probar payloads ya vistos (por defecto se omiten).
REPETIR = os.environ.get("REPETIR") == "1"
# Si REINICIAR=1, se aparta la evidencia anterior (.bak) y se arranca de cero.
REINICIAR = os.environ.get("REINICIAR") == "1"
# Payload especial que el modelo puede incluir entre sus experimentos para
# pedir un reset del estado a mitad de una secuencia.
PAYLOAD_RESET = "__RESET__"


def _es_razonador(modelo):
    """True para modelos que rechazan 'temperature' / razonan antes de responder."""
    m = (modelo or "").lower()
    return any(s in m for s in ("/o1", "/o3", "/o4", "deepseek-r1", "-r1",
                                "reasoning", "qwq", "thinking"))


# ----------------------------------------------------------------------------
# Utilidades de comparación (mismas reglas que el juez del reto)
# ----------------------------------------------------------------------------
def _json_canonico(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _texto_cuerpo(body):
    if isinstance(body, (dict, list)):
        return _json_canonico(body)
    if body is None:
        return ""
    return str(body)


def cuerpos_iguales(a, b):
    """JSON: claves sin importar el orden, arrays en orden, 0 != 0.0.
    Si alguno no es JSON: texto exacto."""
    a_json = isinstance(a, (dict, list))
    b_json = isinstance(b, (dict, list))
    if a_json and b_json:
        return _json_canonico(a) == _json_canonico(b)
    return _texto_cuerpo(a) == _texto_cuerpo(b)


def _rechaza_control(status, body):
    """True si la respuesta indica que el CONTROL fue rechazado (no por
    formato). Sirve para leer, en los experimentos, qué control ACEPTA el
    servicio real para una base."""
    if not isinstance(body, dict):
        return False
    mensaje = (body.get("mensaje") or "").lower()
    if "control" not in mensaje:
        return False
    if "mal formado" in mensaje or "formato" in mensaje:
        return False
    return True


def _codigo_error(body):
    if isinstance(body, dict):
        for clave in ("error", "codigo", "code"):
            valor = body.get(clave)
            if isinstance(valor, str):
                return valor
    return None


def _clasificar_status(status):
    return "éxito" if isinstance(status, int) and 200 <= status < 300 else "error"


def _norm_payload(payload):
    """Clave para detectar repeticiones. El COMANDO es case-insensitive, así que
    'PING;64' y 'ping;64' cuentan como el mismo payload (no gastamos en variar
    mayúsculas)."""
    return (payload or "").strip().upper()


# Catálogo de errores -> (nombre legible, variable que lo causa).
_CATALOGO_ERRORES = {
    "E103": ("falta_control", "PROTOCOLO"),
    "E104": ("segmento_vacio", "PROTOCOLO"),
    "E201": ("control_mal_formado", "CONTROL"),
    "E202": ("control_rechazado", "CONTROL"),
    "E301": ("comando_desconocido", "COMANDO"),
    "E302": ("aridad_invalida", "ARIDAD"),
    "E401": ("cuenta_inexistente", "ESTADO"),
    "E402": ("operacion_inexistente", "ESTADO"),
    "E506": ("limite_excedido", "NEGOCIO"),
    "E507": ("saldo_insuficiente", "NEGOCIO"),
}


def clasificar_respuesta(status, body):
    """Devuelve (clase, variable). 'variable' dice QUÉ dimensión falló, para
    que el modelo no atribuya al CONTROL un error de ESTADO."""
    if isinstance(status, int) and 200 <= status < 300:
        return ("exito", "-")
    cod = _codigo_error(body)
    if cod in _CATALOGO_ERRORES:
        return _CATALOGO_ERRORES[cod]
    if cod:
        return (f"error_{cod}", "DESCONOCIDO")
    return ("error_desconocido", "DESCONOCIDO")


# ----------------------------------------------------------------------------
# Ejecución de código de la IA en un namespace limpio (= servidor reseteado)
# ----------------------------------------------------------------------------
def _ejecutar_codigo(codigo_python):
    entorno = {}
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        exec(codigo_python, entorno, entorno)
    finally:
        sys.stdout = old_stdout
    return entorno


def _limpiar_codigo(texto):
    """Quita los cercos markdown de un bloque de código, si los hay."""
    if not isinstance(texto, str):
        return texto
    bloques = re.findall(r"```(?:python)?(.*?)```", texto, flags=re.DOTALL | re.IGNORECASE)
    if bloques:
        return "\n\n".join(b.strip() for b in bloques)
    return texto.strip()


def _bloques_python(texto):
    """Todos los bloques ```python del texto."""
    return [b.strip() for b in
            re.findall(r"```python\s*(.*?)```", texto, flags=re.DOTALL | re.IGNORECASE)]


def _nombres_funciones(codigo):
    return set(re.findall(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", codigo, flags=re.MULTILINE))


# ----------------------------------------------------------------------------
# Almacén de patrones (evidencia acumulada)
# ----------------------------------------------------------------------------
class Almacen:
    """Acumula TODA la evidencia en `patrones_encontrados.jsonl` y las
    respuestas nuevas en `pruebas/ejemplos_nuevos.jsonl`.

    Cada registro (salvo los especiales) tiene:
      tipo: "replay" | "experimento" | "reset"
      sesion: identificador de la sesión (cada sesión arranca tras un reset)
      paso: posición dentro de la sesión
      payload, observado={status, body}, prediccion, coincide, motivo, clase, ts
    """

    def __init__(self):
        self.f_jsonl = open(PATRONES_JSONL, "a", encoding="utf-8")
        self.f_nuevos = open(EJEMPLOS_NUEVOS, "a", encoding="utf-8")
        self._n_nuevo = self._max_n()
        self._vistos = self._cargar_vistos()

    def _cargar_vistos(self):
        """Payloads (normalizados) que ya están en ejemplos_nuevos, para no
        volver a guardarlos (el usuario no quiere repetidos ahí)."""
        vistos = set()
        if not os.path.exists(EJEMPLOS_NUEVOS):
            return vistos
        with open(EJEMPLOS_NUEVOS, "r", encoding="utf-8") as f:
            for linea in f:
                if not linea.strip():
                    continue
                try:
                    d = json.loads(linea)
                    vistos.add(_norm_payload((d.get("request") or {}).get("m")))
                except Exception:
                    pass
        return vistos

    def _max_n(self):
        if not os.path.exists(EJEMPLOS_NUEVOS):
            return 0
        n = 0
        with open(EJEMPLOS_NUEVOS, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    n = max(n, json.loads(linea).get("n", 0))
        return n

    def registrar(self, registro):
        registro.setdefault("ts", int(time.time()))
        self.f_jsonl.write(json.dumps(registro, ensure_ascii=False) + "\n")
        self.f_jsonl.flush()
        return registro

    def nuevo_ejemplo(self, payload, status, response, seq, hipotesis):
        # Sólo guardamos payloads NUEVOS (normalizados): ni repetidos ni replay.
        norm = _norm_payload(payload)
        if norm in self._vistos:
            return None
        self._vistos.add(norm)
        self._n_nuevo += 1
        fila = {
            "n": self._n_nuevo,
            "id": self._n_nuevo,
            "seq": seq,
            "request": {"m": payload},
            "status": status,
            "response": response,
            "hipotesis": hipotesis,
            "capturado_en": int(time.time()),
        }
        self.f_nuevos.write(json.dumps(fila, ensure_ascii=False) + "\n")
        self.f_nuevos.flush()
        return fila

    def cerrar(self):
        self.f_jsonl.close()
        self.f_nuevos.close()

    # --- lectura ---
    @staticmethod
    def cargar():
        if not os.path.exists(PATRONES_JSONL):
            return []
        regs = []
        with open(PATRONES_JSONL, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    try:
                        regs.append(json.loads(linea))
                    except Exception:
                        pass
        return regs

    @staticmethod
    def sesiones():
        """Devuelve {sesion: [pasos ordenados]} con los pasos observables
        (replay/experimento) y los resets intermedios."""
        regs = Almacen.cargar()
        ses = {}
        for r in regs:
            sid = r.get("sesion")
            if sid is None:
                continue
            ses.setdefault(sid, []).append(r)
        for sid in ses:
            ses[sid].sort(key=lambda r: r.get("paso", 0))
        return ses


def reiniciar_evidencia():
    """Aparta la evidencia anterior a .bak y deja el terreno limpio."""
    for ruta in (PATRONES_JSONL, EJEMPLOS_NUEVOS):
        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            try:
                os.replace(ruta, ruta + ".bak")
                print(f"[*] Evidencia anterior apartada en {os.path.basename(ruta)}.bak")
            except Exception as e:
                print(f"[!] No se pudo apartar {ruta}: {e}")


# ----------------------------------------------------------------------------
# Evidencia derivada (pistas) para el modelo — solo a partir de lo observado
# ----------------------------------------------------------------------------
def extraer_controles(pasos):
    """Pares (base -> controles aceptados) a partir de las observaciones.
    La base se normaliza a MAYÚSCULAS porque el control se calcula sobre la base
    en mayúsculas (evidencia: 'CONSULTa;AC-0001;14' y 'AlTa;Mateo;3' funcionan);
    así 'PING' y 'ping' colapsan al mismo par y la tabla queda limpia.
    Un control se considera RECHAZADO si la respuesta es E201/E202 (o dice
    'control inválido'), y ACEPTADO en cualquier otro caso (E401/E301/E302...)."""
    aceptados = {}
    for r in pasos:
        payload = r.get("payload")
        obs = r.get("observado") or {}
        if not payload or payload == PAYLOAD_RESET:
            continue
        partes = payload.split(";")
        if len(partes) < 2:
            continue
        base = ";".join(partes[:-1]).strip().upper()
        control = partes[-1]
        if not control.isdigit():
            continue
        if _codigo_error(obs.get("body")) in ("E201", "E202"):
            continue
        if isinstance(obs, dict) and _rechaza_control(obs.get("status"), obs.get("body")):
            continue
        aceptados.setdefault(base, set()).add(control)
    return {b: sorted(cs, key=lambda x: (len(x), x)) for b, cs in aceptados.items()}


def extraer_pistas_aritmeticas(pares):
    """Detecta progresiones aritméticas entre controles de bases que comparten
    prefijo y solo cambian en el número final (p. ej. CONSULTA;AC-0001..0004).
    Devuelve líneas con el Δ observado y, si encuentra un módulo m que hace la
    serie lineal (p. ej. 97), lo señala: es una pista CRÍTICA para el checksum.
    Es pura aritmética sobre lo observado: el modelo sigue teniendo que deducir
    la función exacta."""
    grupos = {}
    for base, cs in pares.items():
        if not cs:
            continue
        v = cs[0]
        if not str(v).isdigit():
            continue
        m = re.match(r"^(.*?)(\d+)$", base)
        if not m:
            continue
        prefijo, num = m.group(1), int(m.group(2))
        grupos.setdefault(prefijo, {})[num] = int(v)

    notas = []
    for prefijo, pts in sorted(grupos.items()):
        if len(pts) < 3:
            continue
        ns = sorted(pts)
        vs = [pts[n] for n in ns]
        deltas = [vs[i + 1] - vs[i] for i in range(len(vs) - 1)]

        # 1) ¿Progresión lineal EXACTA (sin envoltura)? Entonces el módulo NO
        #    está determinado todavía: no afirmamos ninguno.
        d_exacto = None
        for d in range(-80, 81):
            if all(vs[i] - vs[0] == d * (ns[i] - ns[0]) for i in range(len(ns))):
                d_exacto = d
                break
        if d_exacto is not None:
            notas.append(
                f"  f('{prefijo}*') sigue v(n) = {vs[0]} + ({d_exacto})·(n−{ns[0]}) "
                f"EXACTA (Δ={d_exacto}, sin envoltura): valores {vs}. El módulo aún "
                f"no está determinado: falta un punto que envuelva (>99 o <0)."
            )
            continue

        # 2) Hay envoltura: buscar el módulo m MÁS PEQUEÑO (> que el valor máximo)
        #    que con alguna pendiente d explique todos los puntos.
        hallado = None
        for m in range(max(vs) + 1, 261):
            for d in range(-80, 81):
                if all((vs[i] - vs[0]) % m == (d * (ns[i] - ns[0])) % m
                       for i in range(len(ns))):
                    hallado = (m, d)
                    break
            if hallado:
                break
        if hallado:
            m, d = hallado
            notas.append(
                f"  f('{prefijo}*') envuelve: encaja con v(n) = {vs[0]} + ({d})·(n−{ns[0]}) "
                f"[módulo {m}] para {vs}. Que el wrap dé {m} es una pista "
                f"IMPORTANTE: el checksum es módulo {m} (signos de una suma "
                f"ponderada/hash lineal, NO de un CRC seudoaleatorio)."
            )
        else:
            notas.append(
                f"  f('{prefijo}*') con valores {vs}: arranca con Δ={deltas[0]} pero "
                f"no encaja con una progresión lineal módulo simple: busca otra "
                f"estructura (columnas con peso distinto, no solo el último dígito)."
            )
    if not notas:
        notas.append("  (aún no hay ≥3 bases con el mismo prefijo y sufijo numérico)")
    return notas


def agrupar_por_resultado(pasos):
    """Agrupa los payloads por el resultado exacto que devolvió el servicio
    (200, 201, 400 E202, 404 E401...). Es la META-metodología: encontrar qué
    tienen en común los payloads de cada grupo y replicarlos grupo por grupo."""
    tmp = {}
    for r in pasos:
        p = r.get("payload")
        obs = r.get("observado") or {}
        if not p or p == PAYLOAD_RESET:
            continue
        st = obs.get("status")
        clase, _ = clasificar_respuesta(st, obs.get("body"))
        clave = f"{st}" if clase == "exito" else f"{st} {clase}"
        tmp.setdefault(clave, []).append(p)
    return sorted([(k, v) for k, v in tmp.items()], key=lambda kv: -len(kv[1]))


def _control_numerico(payload):
    """True si el último campo del payload es numérico (o el payload es especial/
    protocolo). El control se envía LITERAL: si el modelo deja un placeholder
    ('__CTRL__', 'XX'...), no enviamos y se lo decimos en el feedback."""
    if not payload or payload == PAYLOAD_RESET:
        return True
    partes = payload.rsplit(";", 1)
    if len(partes) < 2:
        return True
    return partes[-1].isdigit()


# Marcadores que el modelo puede usar como campo de control para que el programa
# lo sustituya por el valor que calcula su propia candidata `control(base)`.
_PLACEHOLDERS_CONTROL = {"?", "??", "???", "CTRL", "CTRL?", "AUTO", "__CTRL__"}


def _es_placeholder_control(campo):
    c = (campo or "").strip().strip("<>[]{}").upper()
    return c in _PLACEHOLDERS_CONTROL


def _compilar_funcion(codigo, nombre):
    """Compila un bloque de código y devuelve la función `nombre`, o None."""
    if not codigo:
        return None
    try:
        entorno = _ejecutar_codigo(_limpiar_codigo(codigo))
    except Exception:
        return None
    f = entorno.get(nombre)
    return f if callable(f) else None


def _resolver_placeholder(payload, control_fn):
    """Si el payload termina en un marcador ('?'), lo sustituye por el control
    que calcula `control_fn(base)` (base = payload sin el último campo, en
    mayúsculas). Devuelve el payload resuelto o None si no aplica."""
    if not payload or payload == PAYLOAD_RESET or ";" not in payload:
        return None
    base, campo = payload.rsplit(";", 1)
    if not _es_placeholder_control(campo) or control_fn is None:
        return None
    try:
        val = control_fn(base.strip().upper())
    except Exception:
        return None
    if val is None or not str(val).isdigit():
        return None
    return base + ";" + str(val)


def extraer_errores(pasos):
    """Catálogo de errores observados: código -> {status, mensaje, ejemplo, variable}."""
    catalogo = {}
    for r in pasos:
        obs = r.get("observado") or {}
        body = obs.get("body")
        cod = _codigo_error(body)
        if cod and cod not in catalogo:
            clase, variable = clasificar_respuesta(obs.get("status"), body)
            catalogo[cod] = {
                "status": obs.get("status"),
                "mensaje": body.get("mensaje") if isinstance(body, dict) else None,
                "ejemplo": r.get("payload"),
                "variable": variable,
            }
    return catalogo


def payloads_probados(pasos):
    """Conjunto de payloads ya enviados al servicio (para no repetirlos)."""
    vistos = {}
    for r in pasos:
        p = r.get("payload")
        if not p or p == PAYLOAD_RESET:
            continue
        vistos.setdefault(p, 0)
        vistos[p] += 1
    return vistos


def construir_evidencia(ejemplos, sesiones):
    """Arma el bloque de texto con TODA la evidencia que ve el modelo."""
    replay = sesiones.get("replay", [])
    mapa_actual = {}
    for r in replay:
        mapa_actual[r.get("payload")] = r.get("observado")

    lineas_ejemplos = ["EJEMPLOS ORIGINALES (capturados en la mañana) y su estado ACTUAL:"]
    for e in ejemplos:
        actual = mapa_actual.get(e["payload"])
        cambio = ""
        if actual is not None:
            if actual.get("status") == e["status"] and cuerpos_iguales(actual.get("body"), e["response"]):
                cambio = " [SIGUE IGUAL]"
            else:
                cambio = " [CAMBIÓ]"
        else:
            cambio = " [no re-verificado]"
        lineas_ejemplos.append(
            f"  n={e['n']} '{e['payload']}' -> mañana: {e['status']} "
            f"{json.dumps(e['response'], ensure_ascii=False)}"
        )
        if actual is not None:
            lineas_ejemplos.append(
                f"      ahora: {actual.get('status')} "
                f"{json.dumps(actual.get('body'), ensure_ascii=False)}{cambio}"
            )

    todos = [r for pasos in sesiones.values() for r in pasos]
    controles = extraer_controles(todos)
    errores = extraer_errores(todos)
    probados = payloads_probados(todos)
    pistas = extraer_pistas_aritmeticas(controles)
    grupos = agrupar_por_resultado(todos)

    # 2) TABLA CLAVE: base -> control aceptado (lo más importante para el modelo).
    lineas_pares = ["### TABLA CLAVE — par (base en MAYÚSCULAS -> control ACEPTADO) [¡la pieza a descifrar!]:"]
    if controles:
        for base, cs in sorted(controles.items()):
            lineas_pares.append(f"  f('{base}') = {', '.join(cs)}")
        lineas_pares.append(
            "  (El control es una FUNCIÓN DETERMINISTA de la base: mismo base -> "
            "mismo control. NO es una constante ni depende de la sesión.)"
        )
    else:
        lineas_pares.append("  (ninguno todavía)")

    # 2b) PISTAS ARITMÉTICAS automáticas (progresiones y módulo).
    lineas_pistas = ["### PISTAS ARITMÉTICAS detectadas automáticamente (úsalas para deducir el checksum):"]
    lineas_pistas += pistas

    # 2c) GRUPOS POR RESULTADO: qué payloads comparten desenlace.
    lineas_grupos = ["### GRUPOS POR RESULTADO (metodología: qué tienen en común los de cada grupo,"
                     " replica grupo a grupo; los resueltos NO se vuelven a probar):"]
    if grupos:
        for k, ps in grupos:
            muestra = ", ".join(f"'{p}'" for p in ps[:10])
            lineas_grupos.append(f"  [{k}] x{len(ps)}: {muestra}" + (" ..." if len(ps) > 10 else ""))
    else:
        lineas_grupos.append("  (ninguno)")

    # 3) Observaciones de las ÚLTIMAS 2 sesiones, con la CAUSA clasificada.
    lineas_sesiones = ["### OBSERVACIONES RECIENTES CONTRA EL SERVICIO REAL (últimas 2 sesiones, con tus predicciones):"]
    for sid, pasos in list(sesiones.items())[-2:]:
        lineas_sesiones.append(f"\n  [sesión '{sid}']")
        for r in pasos:
            if r.get("payload") == PAYLOAD_RESET:
                lineas_sesiones.append("    -> (reset de estado)")
                continue
            obs = r.get("observado") or {}
            clase, variable = clasificar_respuesta(obs.get("status"), obs.get("body"))
            marcas = [f"causa={variable}"]
            pred = r.get("prediccion")
            if pred is not None:
                marcas.append("PREDICHO OK" if r.get("coincide") else "PREDICHO MAL")
            if r.get("tipo") == "replay":
                marcas.append("replay")
            linea = (
                f"    {r.get('payload')} -> {obs.get('status')} "
                f"{json.dumps(obs.get('body'), ensure_ascii=False)}  ({clase}; "
                + ", ".join(marcas) + ")"
            )
            lineas_sesiones.append(linea)
            if pred is not None and not r.get("coincide"):
                lineas_sesiones.append(
                    f"        tu predicción era: {pred.get('status')} "
                    f"{json.dumps(pred.get('body'), ensure_ascii=False)}"
                )

    lineas_errores = ["### CATÁLOGO DE ERRORES observados (código -> status/mensaje/variable):"]
    if errores:
        for cod, info in sorted(errores.items()):
            lineas_errores.append(
                f"  {cod}: status {info['status']}, variable={info['variable']}, "
                f"mensaje {info['mensaje']!r} (ej: '{info['ejemplo']}')"
            )
    else:
        lineas_errores.append("  (ninguno todavía)")

    lineas_probados = ["### PAYLOADS YA PROBADOS (NO los repitas; el comando es case-insensitive):"]
    if probados:
        # Ordenar y acotar (normalizado) para no inflar el prompt.
        norm = {}
        for p, n in probados.items():
            k = _norm_payload(p)
            norm[k] = norm.get(k, 0) + n
        for k, n in sorted(norm.items())[-80:]:
            lineas_probados.append(f"  '{k}'" + (f"  (x{n})" if n > 1 else ""))
    else:
        lineas_probados.append("  (ninguno)")

    nota = (
        "INSTRUCCIONES DE PROGRESO: (1) NO repitas nada de 'YA PROBADOS'. (2) "
        "METODOLOGÍA POR GRUPOS: en cada ronda replica PRIMERO los payloads cuyo "
        "resultado ya conoces y que siguen iguales (los [SIGUE IGUAL] de la primera "
        "pasada); agrúpalos por desenlace (200/201/400/404/422), busca qué tienen "
        "en común los de CADA grupo y replica grupo a grupo; los grupos resueltos "
        "se dejan y pasas al siguiente. (3) El tema que desbloquea TODO es la "
        "FUNCIÓN DE CONTROL: usa la TABLA, las PISTAS ARITMÉTICAS (módulo!) y el "
        "lab. Para reunir pares (base -> control) NO necesitas estado: prueba bases "
        "NUEVAS de ALTA (E202 = control malo; otro resultado = control ACEPTADO)."
    )

    return "\n".join(
        [nota, ""]
        + lineas_pares
        + ["\n"]
        + lineas_pistas
        + ["\n"]
        + lineas_grupos
        + ["\n"]
        + lineas_ejemplos
        + ["\n"]
        + lineas_sesiones
        + ["\n"]
        + lineas_errores
        + ["\n"]
        + lineas_probados
    )


# ----------------------------------------------------------------------------
# Laboratorio del control: evalúa una candidata f(base) SIN gastar requests
# ----------------------------------------------------------------------------
def evaluar_control(codigo, pares):
    """Evalúa `control(base)` contra todos los pares conocidos.
    Devuelve None si no hay candidata; si la hay: (aciertos, total, fallos)."""
    if not codigo or not pares:
        return None
    try:
        entorno = _ejecutar_codigo(codigo)
    except Exception as e:
        return (0, len(pares), [("", "", f"<excepción al cargar: {e}>")])
    f = entorno.get("control")
    if not callable(f):
        return None
    aciertos = 0
    fallos = []
    for base, esperados in pares.items():
        esperados_str = {str(x) for x in esperados}
        try:
            val = f(base)
        except Exception as e:
            fallos.append((base, sorted(esperados_str), f"<excepción: {e}>"))
            continue
        if str(val) in esperados_str:
            aciertos += 1
        else:
            fallos.append((base, sorted(esperados_str), str(val)))
    return (aciertos, len(pares), fallos)


# ----------------------------------------------------------------------------
# Contrato de la réplica (se inyecta en el prompt)
# ----------------------------------------------------------------------------
CONTRATO_SIMULADOR = """
CONTRATO de la función réplica `simular_caja_negra(payload: str) -> dict`:
- Recibe UN payload (el string de {"m": ...}) y devuelve SIEMPRE un dict con
  EXACTAMENTE dos claves:
    "status": el código HTTP entero.
    "body": el cuerpo EXACTO (objeto Python equivalente si el servidor devuelve
            JSON; string si devuelve texto).
- El ESTADO (cuentas, saldos, contador de operacionId, operaciones anuladas...)
  vive en variables a NIVEL DE MÓDULO, para que llamadas sucesivas reflejen el
  efecto acumulado. El estado inicial de un módulo recién cargado debe ser el de
  un servidor tras POST /__reset.
- Nunca devuelvas None: si dudas, decide un comportamiento por defecto razonable.
"""

CONTRATO_CONTROL = """
CONTRATO de la candidata de control `control(base: str) -> str`:
- Recibe la base SIN el último campo (p. ej. 'CONSULTA;AC-0001').
- Devuelve el control que crees que ACEPTA el servicio para esa base.
- El programa la evalúa GRATIS contra TODOS los pares (base -> control) ya
  observados y te devuelve dónde falla. Itera aquí hasta acertar todos los
  pares. ATENCIÓN: una TABLA que memoriza los pares también da 'todos correctos'
  pero NO generaliza; el lab no distingue memorizar de generalizar. La única
  prueba real de generalización es el marcador ';?' en bases NUEVAS (ver abajo).
- Pista fuerte: los controles observados son un CHECKSUM (hash/mod) de la base,
  módulo 97. Un valor constante es casi seguro erróneo.
- RECETA YA VERIFICADA a mano contra todos los pares (empieza por AQUÍ, no la
  reinventes; confírmala en el lab y úsala para atacar lo que falte):
    * H = hash de Horner base 10 mod 97 sobre SOLO las letras/dígitos de los
      argumentos (todo lo que va tras el primer ';'), EN MAYÚSCULAS y sin '-'
      ni ';' (p. ej. args de 'DEPOSITO;AC-0001;250000' -> 'AC0001250000').
    * m = longitud de ese texto limpio.
    * control = (82 + 94*H + (10**m mod 97)*semilla[COMANDO]) mod 97.
    * Semillas VERIFICADAS: CONSULTA=8, DEPOSITO=22, TRANSFER=53, ANULA=41,
      PING=79, SALDOS=52.
    * Resultado con dígitos SIN ceros a la izquierda (PING->64, ALTA;MATEO->3).
  Esta receta acierta todos los pares EXCEPTO los de ALTA, que es la ANOMALÍA
  ABIERTA: ninguna semilla constante explica ALTA;LUCIA->82, ALTA;MATEO->3 y
  ALTA;LUCIA;GOMEZ->11 a la vez. TU MISIÓN PRINCIPAL ES CERRAR ALTA: hardcodea
  esos 3 y DESCARTA la anomalía probando nombres NUEVOS con 'ALTA;Nombre;?'
  (una cuenta por nombre): si el control lo calculas bien, recibes 201.
  Candidata concreta para ALTA (ajusta los 3 pares, pruébala en nombres NUEVOS):
      control = (11 + 86*H + 8*(10**m mod 97)) mod 97
  Si acierta en un nombre nuevo (201), ya tienes la regla de ALTA; si no, usa el
  resultado para descartar y proponer otra estructura (p. ej. semilla por
  longitud) SIN volver a probar lo que ya sabes.
- El lab es GRATIS: en CADA ronda envía VARIAS candidatas distintas (1 a 3) y
  AGOTA familias, no repitas la misma idea. Familias a probar (varias a la vez):
    * suma de bytes de la base (ord) mod 97; idem mod 100;
    * suma ponderada por posición i*ord(c) (creciente) y (len-i)*ord(c)
      (decreciente) mod 97; con offset +c;
    * hash POLINÓMICO base b: sum ord(c)*b^k mod 97, en orden directo y reverso,
      para b en {2, 31, 33, 37, 131, 257, 65599};
    * DJB2 (h=5381; h=h*33+ord(c)) y FNV-1 / FNV-1a (32 bits, luego mod 97);
    * suma SOLO de dígitos, SOLO de letras, o de valores 'A'=1..'Z'=26;
    * CRC-16/CRC-32 (varios polinomios) mod 97.
- Cómo usarla sin gastar de más: escribe el payload terminando en ';?' y el
  PROGRAMA sustituye '?' por el valor que devuelve tu `control()` sobre esa base.
  Si el servicio NO responde E202, tu fórmula ACERTÓ esa base nueva.
"""


PLACEHOLDER_AYUDA = """
CONTROL AUTOMÁTICO con el marcador '?' (úsalo para PROBAR GENERALIZACIÓN):
- En tus experimentos, puedes terminar el payload en ';?' en vez de escribir
  dígitos. El programa calcula tu `control()` sobre la base (el payload sin el
  último campo, en MAYÚSCULAS) y sustituye el '?' por ese resultado.
- Cada experimento con '?' es un TEST de tu fórmula en una base NUEVA:
    * si el servicio responde E202 -> tu `control()` FALLÓ en esa base;
    * si responde cualquier otra cosa (p. ej. 201 al crear) -> ACERTÓ.
- Úsalo para (a) verificar una candidata que encaja con TODOS los pares y
  (b) probar MUCHAS bases nuevas barato (ALTA;NombreNuevo;?).
- El bloque ```json debe ser JSON LITERAL: NO escribas expresiones ni '+'
  dentro. Para el control usa '?' (no concatenes código).
"""


# ----------------------------------------------------------------------------
# Llamada al modelo
# ----------------------------------------------------------------------------
def pedir_a_ia(evidencia, ronda, feedback_previo):
    print(f"\n[🤖] Consultando al modelo {MODELO} (ronda {ronda})...")

    prompt = f"""
Eres un AGENTE CIENTÍFICO que hace INGENIERÍA INVERSA de una caja negra HTTP.
Tu misión: descubrir su PATRÓN y construir una función que replique, para cada
payload, el STATUS HTTP y el CUERPO EXACTO, incluida la validación de un campo
de CONTROL opaco y el ESTADO acumulado del servidor.

CÓMO TRABAJAMOS (lee esto con atención):
- Trabajamos en CICLOS. En cada ciclo recibes TODA la evidencia real y el
  resultado de TUS experimentos, TU candidata de control y TU réplica previas.
- SÉ BREVE: no escribas ensayos ni razonamiento en texto. Tu trabajo se demuestra
  con CÓDIGO y experimentos. Como mucho, UNA línea de hipótesis.
- METODOLOGÍA POR GRUPOS (tu hoja de ruta, priorizada):
    1º Los payloads cuyo resultado YA conoces y siguen [SIGUE IGUAL], repícalos
       TAL CUAL desde la primera pasada (busca esa cobertura ya).
    2º Agrúpalos por desenlace (200 / 201 / 400 E202 / 404 E401...): busca qué
       tienen en común los payloads de CADA grupo (mismo comando, mismo control
       válido, mismos campos...). Cada grupo resuelto suma cobertura: replica
       grupo a grupo y NO vuelvas a probar los resueltos.
    3º Con más datos, repite la misma dinámica: agrupar -> buscar lo común ->
       proponer -> probar. Entre más datos, más patrones puedes cruzar.
- El tema que desbloquea TODOS los grupos es la FUNCIÓN DE CONTROL. CADA ronda
  envía de 1 a 3 candidatas `control(base)`; el lab las evalúa TODAS gratis.
- El control se valida ANTES que el comando y antes de comprobar si la cuenta
  existe: para reunir pares (base -> control) NO necesitas crear estado. Prueba
  bases NUEVAS con ALTA (p. ej. 'ALTA;<nombre_nuevo>;?'): si sale E202 tu
  fórmula falló; cualquier otro resultado = control ACEPTADO (y ganas un par).
- Usa las PISTAS ARITMÉTICAS de la evidencia (progresiones y módulo detectado):
  encajan con un checksum lineal módulo m, NO con CRC típico.
- La réplica debe reproducir CONTROL y ESTADO. Mientras no tengas la fórmula,
  puede usar una TABLA con los pares (base -> control) conocidos para ganar
  cobertura YA.

EVIDENCIA ACUMULADA (esto es lo que el programa observó del servicio REAL):
{evidencia}

SEMÁNTICA DE COMPARACIÓN del juez (imítala):
- Objetos JSON: las claves pueden venir en cualquier orden.
- Arrays: en el mismo orden.
- Strings y números: idénticos (0 no es "0").
- Si algún cuerpo no es JSON: texto exacto, carácter por carácter.

{feedback_previo}

REGLAS DEL ENTORNO DE EXPERIMENTOS:
- Tus "experimentos" se ejecutan EN ORDEN como UNA sola sesión, tras un
  POST /__reset inicial. Para cambiar de escenario a mitad de la secuencia,
  incluye el payload especial "{PAYLOAD_RESET}".
- Si vas a operar sobre una cuenta (CONSULTA/DEPOSITO/TRANSFER), primero CREA
  esa cuenta con ALTA en la misma sesión, o el servicio responderá E401.
- El campo de control debe ser dígitos concretos O el marcador '?' (ver
  CONTROL AUTOMÁTICO abajo). Nunca envíes otros placeholders ('__CTRL__', 'XX').
- Cada experimento DEBE incluir tu PREDICCIÓN exacta (status + body).
- Máximo {MAX_EXPERIMENTOS_RONDA} experimentos por ciclo: DENSOS y de ALTO
  valor. No varíes mayúsculas ni repitas lo ya sabido.

{PLACEHOLDER_AYUDA}

{CONTRATO_SIMULADOR}

{CONTRATO_CONTROL}

FORMATO DE TU RESPUESTA (SEPARA los bloques; sé BREVE, sin ensayos):
1) OBLIGATORIO: un bloque ```json SOLO con tu hipótesis (una línea) y tus
   experimentos (SIN código dentro, JSON LITERAL):
```json
{{
  "hipotesis": "una sola línea: qué vas a probar y por qué (<=200 caracteres)",
  "experimentos": [
    {{"payload": "ALTA;NombreNuevo;?", "prediccion": {{"status": 201, "body": {{"cuentaId": "AC-00XX"}}}}, "motivo": "prueba de generalización de mi control()"}},
    {{"payload": "ALGO;arg;44", "prediccion": {{"status": 200, "body": {{...}}}}, "motivo": "una línea"}}
  ],
  "confianza": 0.0
}}
```
2) OBLIGATORIO (de 1 a 3): bloques ```python con tus candidatas de control (el
   lab las evalúa TODAS gratis). DEBE llamarse `control` cada una; prueba VARIAS
   familias/parámetros a la vez (no repitas la misma idea):
```python
def control(base):
    # base = todo menos el último ';'
    return ...
```
3) RECOMENDADO: un bloque ```python con tu réplica (DEBE llamarse
   `simular_caja_negra`). Puedes empezar con una TABLA de los pares
   (base -> control) conocidos y completar después con la fórmula:
```python
def simular_caja_negra(payload):
    ...
```
El programa distingue los bloques ```python por el NOMBRE de la función.
NO escribas párrafos de análisis fuera del JSON.
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload_llm = {
        "model": MODELO,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not _es_razonador(MODELO):
        payload_llm["temperature"] = 0.2
    elif ESFUERZO and ESFUERZO.lower() not in ("none", "off", "0", ""):
        # En o-series, baja el esfuerzo de razonamiento para responder más rápido.
        payload_llm["reasoning"] = {"effort": ESFUERZO.lower()}
        # No pedimos (ni imprimimos) la cadena de razonamiento: solo resultados.
        payload_llm["include_reasoning"] = False
    timeout = 600 if _es_razonador(MODELO) else 300
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload_llm,
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise Exception(f"Error de OpenRouter ({resp.status_code}): {resp.text}")

    contenido = resp.json()["choices"][0]["message"]["content"].strip()
    datos = _extraer_json(contenido)
    if datos is None:
        print("[!] El modelo no devolvió JSON válido; muestro su salida cruda.")
        print(contenido[:2000])
        return None

    # Bloques ```python, clasificados por nombre de función.
    bloques = _bloques_python(contenido)
    replicas = [b for b in bloques if "simular_caja_negra" in _nombres_funciones(b)]
    controles = [b for b in bloques if "control" in _nombres_funciones(b)]
    if replicas:
        datos["replica"] = "\n\n".join(replicas)
    if controles:
        datos["control_candidatas"] = controles

    print("[🧠] Respuesta del modelo recibida y parseada.")
    hip = datos.get("hipotesis") or datos.get("analisis")
    if hip:
        print("[🧠] Hipótesis: " + str(hip).strip().splitlines()[0][:200])
    return datos


def _extraer_json(texto):
    """Extrae un objeto JSON de la respuesta del modelo, sea bloque ```json o
    JSON suelto."""
    candidatos = []
    candidatos += re.findall(r"```json\s*(.*?)```", texto, flags=re.DOTALL | re.IGNORECASE)
    candidatos += re.findall(r"```\s*(.*?)```", texto, flags=re.DOTALL)
    candidatos.append(texto)
    for c in candidatos:
        c = c.strip()
        try:
            return json.loads(c)
        except Exception:
            pass
    # último recurso: recortar del primer '{' al último '}'
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini != -1 and fin != -1 and fin > ini:
        try:
            return json.loads(texto[ini:fin + 1])
        except Exception:
            return None
    return None


# ----------------------------------------------------------------------------
# Fase 1: recolección (replay de los ejemplos contra el servicio real)
# ----------------------------------------------------------------------------
def cargar_ejemplos():
    ejemplos = []
    with open(RUTA_DATASET, "r", encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            d = json.loads(linea)
            ejemplos.append({
                "n": d.get("n"),
                "payload": d["request"]["m"],
                "status": d["status"],
                "response": d.get("response", {}),
            })
    ejemplos.sort(key=lambda e: e["n"] if e["n"] is not None else 0)
    return ejemplos


def fase_recoleccion(cliente, almacen, ejemplos, presupuesto):
    """Reenvía los ejemplos al servicio real (tras un reset) y guarda qué
    responde HOY, comparándolo con lo grabado en la mañana."""
    print("\n" + "=" * 78)
    print("FASE 1 -- RECOLECCIÓN: replay de los ejemplos contra el servicio real")
    print("=" * 78)
    try:
        cliente.reset()
    except Exception as e:
        print(f"[!] No se pudo resetear: {e}")
        return
    almacen.registrar({"tipo": "reset", "sesion": "replay", "paso": 0, "payload": PAYLOAD_RESET})

    iguales = 0
    for i, e in enumerate(ejemplos, start=1):
        if presupuesto.agotado():
            print("[!] Presupuesto agotado durante el replay.")
            break
        try:
            fila = cliente.msg(e["payload"], seq="replay",
                               hipotesis=f"replay del ejemplo n={e['n']}")
        except Exception as ex:
            print(f"[!] Error de red en '{e['payload']}': {ex}")
            continue
        presupuesto.gastar()
        obs = {"status": fila["status"], "body": fila.get("response")}
        clase, variable = clasificar_respuesta(obs["status"], obs["body"])
        coincide = (obs["status"] == e["status"] and cuerpos_iguales(obs["body"], e["response"]))
        if coincide:
            iguales += 1
        marca = "OK " if coincide else "DIF"
        print(f"[{marca}] n={e['n']:>2} '{e['payload']}' -> {obs['status']} "
              f"{json.dumps(obs['body'], ensure_ascii=False)}  ({clase}/{variable})")
        if not coincide:
            print(f"        mañana: {e['status']} {json.dumps(e['response'], ensure_ascii=False)}")
        almacen.registrar({
            "tipo": "replay", "sesion": "replay", "paso": i,
            "payload": e["payload"], "observado": obs,
            "prediccion": {"status": e["status"], "body": e["response"]},
            "coincide": coincide, "motivo": "replay de ejemplo de la mañana",
            "clase": clase, "variable": variable,
        })
    print(f"\n[RESUMEN] {iguales}/{len(ejemplos)} ejemplos siguen idénticos hoy.")


# ----------------------------------------------------------------------------
# Fase 2: ejecución de los experimentos propuestos por el modelo
# ----------------------------------------------------------------------------
def ejecutar_experimentos(cliente, almacen, experimentos, sesion_id, presupuesto,
                          control_fn=None):
    # Payloads YA enviados alguna vez (normalizados, el comando es case-insensitive).
    # No volvemos a gastar requests en ellos: eso es lo que pedía retroalimentación.
    previos = set()
    for r in Almacen.cargar():
        p = r.get("payload")
        if p and p != PAYLOAD_RESET:
            previos.add(_norm_payload(p))

    # Deduplicar dentro de la ronda (salvo los __RESET__, que sí se respetan) y
    # bloquear payloads con control no numérico (placeholder literales).
    vistos = set()
    limpios = []
    omitidos = 0
    no_numericos = 0
    autos = 0
    for exp in experimentos:
        p = exp.get("payload")
        if p == PAYLOAD_RESET:
            limpios.append(exp)
            continue
        # Marcador de control ('?'): lo sustituye nuestra candidata `control(base)`.
        # Esto PRUEBA la generalización de la fórmula en bases NUEVAS (gratis hasta
        # que la enviamos; la respuesta del servicio nos dice si acertó).
        es_auto = False
        resuelto = _resolver_placeholder(p, control_fn)
        if resuelto is not None:
            print(f"    [auto] '{p}' -> '{resuelto}' (control calculado por tu `control()`).")
            exp = dict(exp)
            exp["payload"] = resuelto
            exp["_auto"] = True
            p = resuelto
            es_auto = True
        elif p and ";" in p and _es_placeholder_control(p.rsplit(";", 1)[-1]):
            print(f"    [formato] '{p}': usaste el marcador '?' pero aún no hay una "
                  f"candidata `control()` que sustituya; no se envió.")
            no_numericos += 1
            omitidos += 1
            continue
        if not _control_numerico(p):
            ctrl = p.rsplit(";", 1)[-1] if ";" in p else "(sin control)"
            print(f"    [formato] '{p}': el control '{ctrl}' no es numérico y se "
                  f"envía LITERAL. Pon dígitos concretos (p. ej. '...;44') o el "
                  f"marcador '?' para que el programa lo calcule; no se envió.")
            no_numericos += 1
            omitidos += 1
            continue
        norm = _norm_payload(p)
        if norm in vistos:
            print(f"    [dedup] '{p}' repetido en la ronda; se omite.")
            omitidos += 1
            continue
        if not REPETIR and norm in previos:
            print(f"    [dedup] '{p}' YA se probó antes; se omite (avanza hacia el control).")
            omitidos += 1
            continue
        vistos.add(norm)
        if es_auto:
            autos += 1
        limpios.append(exp)
    experimentos = limpios
    if no_numericos:
        print(f"    [!] {no_numericos} payload(s) con control no numérico descartados "
              f"sin gastar request.")
    if autos:
        print(f"    [auto] {autos} control(es) sustituidos por tu `control()`: esto "
              f"mide si tu fórmula GENERALIZA a bases nuevas.")

    print(f"\n[🧪] Ejecutando {len(experimentos)} experimentos del modelo (sesión '{sesion_id}')...")
    try:
        cliente.reset()
    except Exception as e:
        print(f"[!] No se pudo resetear: {e}")
    almacen.registrar({"tipo": "reset", "sesion": sesion_id, "paso": 0, "payload": PAYLOAD_RESET})

    resultados = []
    paso = 1
    for exp in experimentos:
        if presupuesto.agotado():
            print("[!] Presupuesto agotado; se detienen los experimentos.")
            break
        payload = exp.get("payload")
        pred = exp.get("prediccion")
        motivo = exp.get("motivo", "")
        auto = bool(exp.get("_auto"))
        if payload == PAYLOAD_RESET:
            try:
                cliente.reset()
            except Exception:
                pass
            almacen.registrar({"tipo": "reset", "sesion": sesion_id, "paso": paso,
                               "payload": PAYLOAD_RESET, "motivo": motivo})
            print("    -> (reset solicitado por el modelo)")
            paso += 1
            continue
        try:
            fila = cliente.msg(payload, seq=sesion_id, hipotesis=motivo or "experimento del modelo")
        except Exception as ex:
            print(f"[!] Error de red en '{payload}': {ex}")
            continue
        presupuesto.gastar()
        obs = {"status": fila["status"], "body": fila.get("response")}
        clase, variable = clasificar_respuesta(obs["status"], obs["body"])
        coincide = None
        if pred is not None:
            coincide = (pred.get("status") == obs["status"]
                        and cuerpos_iguales(pred.get("body"), obs["body"]))
        # Para experimentos con control automático ('?') la señal útil NO es si el
        # modelo acertó la predicción, sino si el servicio ACEPTÓ su control.
        if auto:
            acepta = variable != "CONTROL"
            marca = "🟢 control ACEPTADO" if acepta else "🔴 control RECHAZADO (E202)"
        else:
            marca = "✅" if coincide else ("❌" if coincide is False else "·")
        print(f"    {marca} '{payload}' -> "
              f"{obs['status']} {json.dumps(obs['body'], ensure_ascii=False)}  ({clase}/{variable})")
        almacen.registrar({
            "tipo": "experimento", "sesion": sesion_id, "paso": paso,
            "payload": payload, "observado": obs, "prediccion": pred,
            "coincide": coincide, "motivo": motivo, "clase": clase, "variable": variable,
            "auto": auto,
        })
        almacen.nuevo_ejemplo(payload, obs["status"], obs["body"], sesion_id, motivo)
        resultados.append({"payload": payload, "observado": obs, "prediccion": pred,
                           "coincide": coincide, "motivo": motivo, "clase": clase,
                           "variable": variable, "auto": auto})
        paso += 1
    return resultados, omitidos


def formatear_feedback(resultados, replica_score, fallos_replica, desglose=None,
                       control_info=None, spec_previo=None, omitidos=0,
                       falta_control=False, desglose_grupo=None, auto_info=None):
    lineas = ["=== RESULTADO DE TU ÚLTIMO CICLO ==="]
    if spec_previo:
        lineas.append("Tu hipótesis previa (una línea): " + str(spec_previo).strip().splitlines()[0][:200])

    if omitidos:
        lineas.append(
            f"Se OMITIERON {omitidos} experimentos porque ya se habían probado antes. "
            "NO vuelvas a proponerlos: avanza (el tema abierto es el control)."
        )
    if falta_control:
        lineas.append(
            "NO enviaste candidata `control(base)` en el bloque ```python. Es "
            "OBLIGATORIO cada ronda: el laboratorio la evalúa GRATIS."
        )

    if resultados:
        aciertos = sum(1 for r in resultados if r["coincide"] is True)
        con_pred = sum(1 for r in resultados if r["prediccion"] is not None)
        lineas.append(f"Predicciones: {aciertos}/{con_pred} correctas de {len(resultados)} experimentos.")
        for r in resultados:
            obs = r["observado"]
            if r["coincide"] is True:
                est = "ACERTASTE"
            elif r["coincide"] is False:
                est = f"FALLASTE (la causa real fue {r['variable']}, no necesariamente el control)"
            else:
                est = "sin predicción"
            lineas.append(
                f"  - '{r['payload']}' -> real {obs['status']} "
                f"{json.dumps(obs['body'], ensure_ascii=False)}  [{r['clase']}/{r['variable']}] [{est}]"
            )

    if control_info:
        lineas.append(
            f"\nTu candidata `control(base)` acertó {control_info['aciertos']}/"
            f"{control_info['total']} pares (base -> control) conocidos."
        )
        for base, esp, val in control_info["fallos"][:8]:
            lineas.append(f"  - fallo: f('{base}') esperado {esp}, dio {val!r}")
        if control_info["aciertos"] == control_info["total"]:
            lineas.append(
                "  ¡Encaja con TODOS los pares conocidos! OJO: una TABLA memoriza y "
                "el lab NO distingue memorizar de generalizar. Para saber si tu "
                "fórmula GENERALIZA, prueba bases NUEVAS terminando el payload en "
                "';?' (el programa sustituye tu `control()`): cada base nueva aceptada "
                "= tu fórmula acierta; un E202 = tu fórmula falló en esa base."
            )

    if auto_info:
        lineas.append(
            f"\nSe resolvieron {auto_info['total']} experimento(s) con el marcador '?' "
            f"usando tu `control()`. De ellos, {auto_info['fallos']} fueron rechazados "
            f"por CONTROL (E202): tu función NO generaliza a esas bases nuevas."
        )
        for pl in auto_info.get("bases_fallidas", [])[:8]:
            lineas.append(f"  - falló el control de '{pl}'")
        if auto_info["total"] and auto_info["fallos"] == 0:
            lineas.append("  ¡Todas las bases nuevas aceptaron tu control! Examina qué "
                          "tienen en común con las conocidas.")

    if replica_score is not None:
        lineas.append(f"\nTu réplica reprodujo el {replica_score:.0%} de los casos observados.")
        if desglose:
            partes = [f"{cmd}: {ok}/{tot}" for cmd, (ok, tot) in sorted(desglose.items())]
            lineas.append("  Desglose por comando: " + "; ".join(partes))
        if desglose_grupo:
            lineas.append("  Cobertura por GRUPO de resultado (los que están a 0 son tu prioridad):")
            for k, (ok, tot) in sorted(desglose_grupo.items()):
                marca = " ✔" if ok == tot else (" <-- FALTA" if ok == 0 else "")
                lineas.append(f"    {k}: {ok}/{tot}{marca}")
        if fallos_replica:
            lineas.append("Primeros fallos de tu réplica (más tempranos primero):")
            for f in fallos_replica[:8]:
                lineas.append(
                    f"  - sesión '{f['sesion']}' '{f['payload']}': esperado "
                    f"{json.dumps(f['esperado'], ensure_ascii=False)}, tu réplica "
                    f"{json.dumps(f['tu'], ensure_ascii=False)}"
                )

    lineas.append(
        "\nRecuerda: NO repitas lo ya probado y NO re-verifiques reglas confirmadas. "
        "Céntrate en la FUNCIÓN DE CONTROL: propón `control(base)`, mírala en el "
        "laboratorio y verifica en una base NUEVA solo cuando encaje con TODOS los pares."
    )
    return "\n".join(lineas)


# ----------------------------------------------------------------------------
# Fase 3: prueba local de la réplica contra TODAS las sesiones observadas
# ----------------------------------------------------------------------------
def probar_replica(codigo, sesiones, control_codigo=None):
    """Devuelve (score, fallos, desglose, desglose_grupo):
    - desglose: {comando: [ok, total]}
    - desglose_grupo: {resultado (200/201/400 E202/...): [ok, total]}
    `control_codigo` (si se pasa) define `control(base)` en el entorno de la
    réplica, de modo que las llamadas a `control()` del modelo se resuelvan."""
    if not codigo:
        return None, [], {}, {}
    codigo = _limpiar_codigo(codigo)
    # Inyectamos la mejor `control(base)` conocida para que la réplica pueda usarla.
    ctrl = _limpiar_codigo(control_codigo) if control_codigo else ""
    fuente = (ctrl + "\n\n" + codigo) if ctrl else codigo
    total = 0
    ok = 0
    fallos = []
    desglose = {}
    desglose_grupo = {}

    def _cmd(payload):
        return payload.split(";")[0].strip().upper() or "(vacío)"

    def _grupo(obs):
        st = obs.get("status")
        clase, _ = clasificar_respuesta(st, obs.get("body"))
        return f"{st}" if clase == "exito" else f"{st} {clase}"

    for sid, pasos in sesiones.items():
        try:
            entorno = _ejecutar_codigo(fuente)
        except Exception as e:
            return 0.0, [{"sesion": sid, "payload": "<init>", "esperado": None,
                          "tu": f"<excepción al cargar: {e}>"}], desglose, desglose_grupo
        simular = entorno.get("simular_caja_negra")
        if not callable(simular):
            return 0.0, [{"sesion": sid, "payload": "<init>", "esperado": None,
                          "tu": "simular_caja_negra no está definida"}], desglose, desglose_grupo
        for r in pasos:
            payload = r.get("payload")
            obs = r.get("observado")
            if payload == PAYLOAD_RESET:
                try:
                    entorno = _ejecutar_codigo(fuente)
                    simular = entorno.get("simular_caja_negra")
                except Exception as e:
                    return 0.0, [{"sesion": sid, "payload": "<init>", "esperado": None,
                                  "tu": f"<excepción: {e}>"}], desglose, desglose_grupo
                continue
            if obs is None:
                continue
            total += 1
            cmd = _cmd(payload)
            d = desglose.setdefault(cmd, [0, 0])
            d[1] += 1
            g = desglose_grupo.setdefault(_grupo(obs), [0, 0])
            g[1] += 1
            try:
                res = simular(payload)
            except Exception as e:
                fallos.append({"sesion": sid, "payload": payload,
                               "esperado": obs, "tu": f"<excepción: {e}>"})
                continue
            if not isinstance(res, dict):
                fallos.append({"sesion": sid, "payload": payload,
                               "esperado": obs, "tu": f"<no dict: {res!r}>"})
                continue
            if (res.get("status") == obs.get("status")
                    and cuerpos_iguales(res.get("body"), obs.get("body"))):
                ok += 1
                d[0] += 1
                g[0] += 1
            else:
                fallos.append({"sesion": sid, "payload": payload, "esperado": obs,
                               "tu": {"status": res.get("status"), "body": res.get("body")}})
    score = ok / total if total else 0.0
    return score, fallos, desglose, desglose_grupo


# ----------------------------------------------------------------------------
# main: el ciclo completo
# ----------------------------------------------------------------------------
def main():
    print("=" * 78)
    print("AGENTE CIENTÍFICO -- ciclo completo dirigido por el modelo de OpenRouter")
    print("=" * 78)
    if not OPENROUTER_API_KEY:
        print("[!] ERROR: falta OPENROUTER_API_KEY en el entorno o en el .env.")
        print("    Añádela al .env o expórtala para que el modelo pueda razonar.")
        return

    if REINICIAR:
        print("[*] REINICIAR=1: se aparta la evidencia anterior.")
        reiniciar_evidencia()

    ejemplos = cargar_ejemplos()
    print(f"[*] Modelo: {MODELO}" + ("  (razonador: sin temperature)" if _es_razonador(MODELO) else ""))
    print(f"[*] Cargados {len(ejemplos)} ejemplos de {os.path.relpath(RUTA_DATASET, RAIZ)}")
    print(f"[*] Presupuesto total de requests al servicio real: {PRESUPUESTO_TOTAL}")
    print(f"[*] Máximo de ciclos con el modelo: {MAX_RONDAS}")

    cliente = Cliente()
    almacen = Almacen()
    presupuesto = Presupuesto(PRESUPUESTO_TOTAL)

    try:
        # Fase 1: recolección (solo si no hay replay previo en la evidencia).
        sesiones = Almacen.sesiones()
        if "replay" not in sesiones:
            fase_recoleccion(cliente, almacen, ejemplos, presupuesto)
            sesiones = Almacen.sesiones()
        else:
            print("[*] Ya existe evidencia de replay; no se repite (usa REINICIAR=1 para rehacerla).")

        feedback = ""
        spec_previo = ""
        mejor_replica = {"score": -1.0, "codigo": None}
        mejor_control = {"score": -1.0, "codigo": None}

        for ronda in range(1, MAX_RONDAS + 1):
            print("\n" + "=" * 78)
            print(f"RONDA {ronda}/{MAX_RONDAS} -- el modelo propone patrón + experimentos")
            print("=" * 78)

            sesiones = Almacen.sesiones()
            todos = [r for pasos in sesiones.values() for r in pasos]
            pares = extraer_controles(todos)
            evidencia = construir_evidencia(ejemplos, sesiones)

            try:
                datos = pedir_a_ia(evidencia, ronda, feedback)
            except Exception as e:
                print(f"[!] Error consultando al modelo: {e}. Reintentando en la próxima ronda.")
                feedback = f"(Error de infraestructura en la ronda anterior: {e})"
                continue
            if not datos:
                feedback = "Tu respuesta anterior no fue JSON válido. Devuelve SOLO el bloque ```json."
                continue

            if datos.get("hipotesis"):
                spec_previo = datos["hipotesis"]
            elif datos.get("analisis"):
                spec_previo = str(datos["analisis"]).strip().splitlines()[0][:200]

            # --- Laboratorio de control (GRATIS) ---
            control_info = None
            for cand in (datos.get("control_candidatas") or []):
                res = evaluar_control(cand, pares)
                if not res:
                    continue
                a, t, fallos_c = res
                print(f"[🧪lab] Candidata `control(base)`: {a}/{t} pares correctos.")
                for base, esp, val in fallos_c[:6]:
                    print(f"        f('{base}') esperado {esp}, dio {val!r}")
                if a == t:
                    print("[🧪lab] ¡La candidata encaja con TODOS los pares conocidos! "
                          "(una TABLA también; el lab no distingue memorizar de "
                          "generalizar: usa ';?' en bases NUEVAS para comprobarlo).")
                if t and a / t > mejor_control["score"]:
                    mejor_control = {"score": a / t, "codigo": cand}
                if control_info is None or (t and a / t > control_info["aciertos"] / max(1, control_info["total"])):
                    control_info = {"aciertos": a, "total": t, "fallos": fallos_c, "codigo": cand}

            # --- Prompt DINÁMICO según el output del lab ---
            # Si la mejor candidata solo falla en ALTA, no le hagas re-probar lo ya
            # resuelto: empújale a cazar la anomalía con nombres NUEVOS.
            pista_dinamica = ""
            if control_info and control_info.get("fallos"):
                bases_fallidas = [str(b).upper() for b, _, _ in control_info["fallos"]]
                if bases_fallidas and all(b.startswith("ALTA;") for b in bases_fallidas):
                    pista_dinamica = (
                        "Tu `control()` acierta TODOS los pares salvo los de ALTA. ALTA es la "
                        "ANOMALÍA ABIERTA: céntrate SOLO en ALTA. Lanza 'ALTA;Nombre;?' con "
                        "nombres NUEVOS y variados (longitudes distintas, con espacio, "
                        "mayúsculas/minúsculas) e intenta ver qué la distingue del resto "
                        "(¿semilla propia? ¿el nombre se hashea distinto? ¿cuenta su longitud?).")
                    print("[🧪lab] " + pista_dinamica)

            # --- Réplica propuesta ---
            # `control` que inyectamos en la réplica: la mejor candidata conocida
            # (normalmente la tabla completa), para que `control(base)` resuelva.
            control_replica = None
            if mejor_control.get("codigo"):
                control_replica = mejor_control["codigo"]
            elif control_info and control_info.get("codigo"):
                control_replica = control_info["codigo"]
            replica_codigo = datos.get("replica")
            score, fallos, desglose = None, [], {}
            desglose_grupo = {}
            if replica_codigo in (None, "", "null"):
                replica_codigo = None
            else:
                replica_codigo = _limpiar_codigo(replica_codigo)
                score, fallos, desglose, desglose_grupo = probar_replica(
                    replica_codigo, sesiones, control_codigo=control_replica)
                print(f"[🔬] Réplica propuesta: reproduce {score:.0%} de la evidencia acumulada.")
                if score is not None and score > mejor_replica["score"]:
                    mejor_replica = {"score": score, "codigo": replica_codigo}
            # Si el modelo no mandó réplica, seguimos con la mejor guardada.
            if replica_codigo is None and mejor_replica["codigo"]:
                score, fallos, desglose, desglose_grupo = probar_replica(
                    mejor_replica["codigo"], sesiones, control_codigo=control_replica)
                replica_codigo = mejor_replica["codigo"]
                print(f"[🔬] Reutilizo la mejor réplica guardada: {score:.0%}.")

            # --- Experimentos ---
            experimentos = datos.get("experimentos") or []
            if isinstance(experimentos, dict):
                experimentos = [experimentos]
            experimentos = [e for e in experimentos
                            if isinstance(e, dict) and e.get("payload")][:MAX_EXPERIMENTOS_RONDA]

            resultados = []
            omitidos = 0
            auto_info = None
            if experimentos and not presupuesto.agotado():
                sesion_id = f"ronda_{ronda}"
                # Para el marcador '?': usa la candidata de ESTA ronda si existe
                # (así el modelo prueba su última idea), si no la mejor guardada.
                codigo_ctrl = None
                if control_info and control_info.get("codigo"):
                    codigo_ctrl = control_info["codigo"]
                elif mejor_control.get("codigo"):
                    codigo_ctrl = mejor_control["codigo"]
                control_fn = _compilar_funcion(codigo_ctrl, "control")
                resultados, omitidos = ejecutar_experimentos(
                    cliente, almacen, experimentos, sesion_id, presupuesto,
                    control_fn=control_fn)
                # ¿Cómo le fue a la fórmula en las bases NUEVAS (marcador '?')?
                auto_res = [r for r in resultados if r.get("auto")]
                if auto_res:
                    fallidas = [r["payload"] for r in auto_res if r["variable"] == "CONTROL"]
                    auto_info = {"total": len(auto_res), "fallos": len(fallidas),
                                 "bases_fallidas": fallidas}
                # Re-evaluar contra la evidencia NUEVA.
                sesiones = Almacen.sesiones()
                todos = [r for pasos in sesiones.values() for r in pasos]
                pares = extraer_controles(todos)
                if replica_codigo:
                    score, fallos, desglose, desglose_grupo = probar_replica(
                        replica_codigo, sesiones, control_codigo=control_replica)
                    print(f"[🔬] Réplica re-evaluada con la evidencia nueva: {score:.0%}.")
                    if score is not None and score > mejor_replica["score"]:
                        mejor_replica = {"score": score, "codigo": replica_codigo}
                if control_info and control_info.get("codigo"):
                    res = evaluar_control(control_info["codigo"], pares)
                    if res:
                        control_info["aciertos"], control_info["total"], control_info["fallos"] = res
            elif presupuesto.agotado():
                print("[!] Presupuesto total agotado: ya no se pueden ejecutar más experimentos.")

            # Cobertura por grupo (cuáles ya replica y cuáles faltan).
            if desglose_grupo:
                partes = [f"{k}: {ok}/{tot}" for k, (ok, tot) in sorted(desglose_grupo.items())]
                print("[📈] Réplica por grupo: " + " · ".join(partes))

            falta_control = not (datos.get("control_candidatas"))
            feedback = formatear_feedback(resultados, score, fallos, desglose,
                                          control_info, spec_previo,
                                          omitidos=omitidos, falta_control=falta_control,
                                          desglose_grupo=desglose_grupo,
                                          auto_info=auto_info)
            if pista_dinamica:
                feedback = pista_dinamica + "\n" + feedback

            # --- ¿Éxito? ---
            # Réplica 100% sobre replay + al menos una sesión de experimentos
            # (diferencial real) y, si hay candidata de control, que encaje todo.
            control_ok = (control_info is None) or (control_info["aciertos"] == control_info["total"])
            if replica_codigo and score == 1.0 and len(sesiones) > 1 and control_ok:
                print("\n" + "🎉" * 30)
                print("¡RÉPLICA CONFIRMADA! Reproduce el 100% de toda la evidencia real "
                      "(replay + experimentos del modelo).")
                print("=" * 78)
                print(replica_codigo)
                _guardar_replica(replica_codigo)
                if mejor_control["codigo"]:
                    _guardar_control(mejor_control["codigo"])
                return

            if presupuesto.agotado():
                print("\n[⚠️] Presupuesto agotado. Guardo la mejor réplica y la evidencia.")
                break

        # Fin de rondas o presupuesto.
        print("\n" + "=" * 78)
        print(f"[FIN] Mejor réplica: {mejor_replica['score']:.0%}. "
              f"Mejor candidata de control: {mejor_control['score']:.0%}.")
        print(f"[*] Evidencia acumulada en {os.path.relpath(PATRONES_JSONL, RAIZ)}")
        if mejor_replica["codigo"]:
            print("\n[Código de la mejor réplica]:\n" + mejor_replica["codigo"])
            _guardar_replica(mejor_replica["codigo"])
        if mejor_control["codigo"]:
            print("\n[Candidata de control]:\n" + mejor_control["codigo"])
            _guardar_control(mejor_control["codigo"])
    finally:
        almacen.cerrar()


def _guardar_replica(codigo):
    ruta = os.path.join(RAIZ, "replica", "simulador_ia.py")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
        print(f"[*] Réplica guardada en {os.path.relpath(ruta, RAIZ)}")
    except Exception as e:
        print(f"[!] No se pudo guardar la réplica: {e}")


def _guardar_control(codigo):
    ruta = os.path.join(RAIZ, "replica", "control_ia.py")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
        print(f"[*] Candidata de control guardada en {os.path.relpath(ruta, RAIZ)}")
    except Exception as e:
        print(f"[!] No se pudo guardar el control: {e}")


class Presupuesto:
    def __init__(self, tope):
        self.tope = tope
        self.usado = 0

    def agotado(self):
        return self.usado >= self.tope

    def gastar(self):
        self.usado += 1
        if self.usado % 25 == 0:
            print(f"    [presupuesto] {self.usado}/{self.tope} requests usados.")


if __name__ == "__main__":
    main()
