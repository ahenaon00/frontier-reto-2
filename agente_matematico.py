import os
import json
import requests
import re
import sys
import io
import random

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from explorador.cliente import Cliente

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
API_KEY = OPENROUTER_API_KEY
# Usando GPT-4o (Lógica Suprema) para deducción científica
MODELO = "openai/gpt-4o"

# --- Config de la fase actual ---
# FASE 1: la IA solo necesita acertar el STATUS HTTP de cada caso (en orden).
# El cuerpo completo de la respuesta se guarda para fases futuras pero NO se
# evalúa todavía.
RUTA_DATASET = os.path.join("pruebas", "ejemplos.jsonl")
MAX_INTENTOS = 20
# Comandos que se consideran "seguros" para probar en vivo contra el servidor
# real (evitamos comandos que crean entidades nuevas de forma indefinida,
# como ALTA, para no ensuciar el estado real del backend).
COMANDOS_PROBABLES_EN_VIVO = ["CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"]


def cargar_casos_empiricos(ruta_archivo):
    """Carga el dataset conservando orden y la respuesta completa.

    El cuerpo completo (`response_real`) se guarda ya desde ahora aunque en
    esta fase no se valide, para no tener que volver a tocar esta función
    cuando pasemos a exigir réplica completa de las respuestas.
    """
    casos = []
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        for linea in f:
            if not linea.strip():
                continue
            dato = json.loads(linea)
            casos.append({
                "n": dato.get("n"),
                "payload": dato["request"]["m"],
                "status_real": dato["status"],
                "response_real": dato.get("response", {}),
            })
    # Nos aseguramos de procesarlos en el orden real de la sesión: varios
    # status (saldo insuficiente, límite excedido, cuenta inexistente...)
    # dependen del historial previo, no solo del payload individual.
    casos.sort(key=lambda c: c["n"] if c["n"] is not None else 0)
    return casos


def _clasificar_status(status):
    """2xx -> 'éxito'; cualquier otra cosa -> 'error'. Sirve para etiquetar
    si un fallo del simulador fue un falso positivo o un falso negativo."""
    if isinstance(status, int) and 200 <= status < 300:
        return "éxito"
    return "error"


def detectar_pares_contraste(casos_empiricos):
    """Agrupa casos que comparten TODO el payload excepto el último campo
    (el "control"). Si dentro de un mismo grupo hay status distintos, eso es
    la evidencia más directa de que el control determina el resultado —
    se la servimos a la IA ya masticada en vez de esperar a que la
    encuentre sola entre 20 casos sueltos.
    """
    grupos = {}
    for c in casos_empiricos:
        partes = c["payload"].split(";")
        if len(partes) < 2:
            continue
        clave = ";".join(partes[:-1])  # comando + args, sin el control
        grupos.setdefault(clave, []).append(c)

    pares = []
    for clave, lista in grupos.items():
        estados = {c["status_real"] for c in lista}
        if len(lista) >= 2 and len(estados) > 1:
            pares.append(lista)
    return pares


def formatear_pares_contraste(pares_contraste):
    if not pares_contraste:
        return "(no se detectaron pares de contraste automáticamente)"
    bloques = []
    for grupo in pares_contraste:
        lineas = "\n".join(
            f"    - '{c['payload']}' -> status {c['status_real']}" for c in grupo
        )
        bloques.append(lineas)
    return "\n".join(bloques)


def extraer_controles_confirmados(casos_empiricos):
    """Extrae pares (base, control) donde ya sabemos con certeza si ese
    control fue ACEPTADO o RECHAZADO por el validador de control, usando
    únicamente el texto del propio mensaje de error (sin hardcodear códigos
    de error, para que esto siga funcionando si cambia el dataset).

    - "válido": el mensaje de error (si lo hay) NO menciona la palabra
      "control" -> lo que haya fallado, falló DESPUÉS de validar el control,
      así que el control en sí era el correcto para ese payload.
    - "inválido": el mensaje SÍ menciona "control" pero no dice que esté
      "mal formado" / sea un problema de "formato" -> el control tenía el
      formato correcto (ej. era numérico) pero el VALOR era el incorrecto.
      Este es un ejemplo negativo valiosísimo: nos dice qué valor NO
      produce la fórmula correcta para esa base.

    Casos de "mal formado" (ej. '5X') se descartan: no nos dicen nada sobre
    la fórmula, solo que ni siquiera parecía un número.
    """
    validos, invalidos = [], []
    vistos_validos, vistos_invalidos = set(), set()

    for c in casos_empiricos:
        partes = c["payload"].split(";")
        if len(partes) < 2:
            continue
        base = ";".join(partes[:-1])
        control = partes[-1]
        mensaje = (c["response_real"].get("mensaje") or "").lower()

        if "control" in mensaje:
            if "mal formado" in mensaje or "formato" in mensaje:
                continue
            clave = (base, control)
            if clave not in vistos_invalidos:
                vistos_invalidos.add(clave)
                invalidos.append((base, control))
        else:
            clave = (base, control)
            if clave not in vistos_validos:
                vistos_validos.add(clave)
                validos.append((base, control))

    return validos, invalidos


def formatear_controles_confirmados(validos, invalidos):
    if not validos and not invalidos:
        return "(no se pudo confirmar ningún control automáticamente)"
    lineas = []
    if validos:
        lineas.append("  Controles CORRECTOS confirmados (base -> control que SÍ fue aceptado):")
        for base, control in validos:
            lineas.append(f"    '{base}' -> {control}")
    if invalidos:
        lineas.append("  Controles INCORRECTOS confirmados (formato válido, pero el valor NO era el esperado):")
        for base, control in invalidos:
            lineas.append(f"    '{base}' -> {control}  (RECHAZADO)")
    return "\n".join(lineas)


def extraer_anulaciones_confirmadas(casos_empiricos):
    """Reconstruye, de forma genérica (sin asumir nada propio de este
    dataset más allá de la forma "operacionId" / "ANULA;<id>;<control>"),
    qué operaciones fueron efectivamente REVERTIDAS durante la sesión
    empírica.

    Para cada caso cuya respuesta real trae un "operacionId" (es decir,
    una operación que nació con éxito), busca si MÁS ADELANTE en la
    sesión aparece un "ANULA" sobre ese mismo id cuya respuesta real diga
    ok=True. Si es así, esa operación quedó anulada desde ese punto de la
    sesión en adelante.

    Esto existe porque el estado acumulado por sí solo (saldos, contadores)
    no basta como pista: con solo 20 casos sueltos la IA tiende a modelar
    ANULA como "marcar un flag" y olvida que también debe deshacer el
    efecto de la operación (p.ej. el movimiento de saldo de un DEPOSITO o
    TRANSFER) para que los casos posteriores cuadren.
    """
    creadoras_por_op = {}
    for c in casos_empiricos:
        op_id = (c.get("response_real") or {}).get("operacionId")
        if op_id and op_id not in creadoras_por_op:
            creadoras_por_op[op_id] = c

    anulaciones = []
    for c in casos_empiricos:
        partes = c["payload"].split(";")
        if not partes or partes[0].strip().upper() != "ANULA" or len(partes) < 2:
            continue
        op_id = partes[1]
        resp = c.get("response_real") or {}
        if resp.get("ok") is True and op_id in creadoras_por_op:
            creador = creadoras_por_op[op_id]
            anulaciones.append({
                "payload_creador": creador["payload"],
                "n_creador": creador["n"],
                "payload_anula": c["payload"],
                "n_anula": c["n"],
            })
    return anulaciones


def formatear_anulaciones_confirmadas(anulaciones):
    if not anulaciones:
        return "(no se detectó ninguna anulación exitosa automáticamente en los datos)"
    lineas = []
    for a in anulaciones:
        lineas.append(
            f"    - La operación creada en n={a['n_creador']} ('{a['payload_creador']}') "
            f"fue ANULADA CON ÉXITO en n={a['n_anula']} ('{a['payload_anula']}'). "
            "A PARTIR de ese punto de la sesión (para todos los casos con n mayor), "
            "el efecto de esa operación sobre el estado (saldos, etc.) debe "
            "tratarse como REVERTIDO, no solo como 'marcado'."
        )
    return "\n".join(lineas)


# --- Contrato estricto de generar_payload --------------------------------
# Bloque de texto inyectado literal en el prompt (ver pedir_codigo_a_ia).
# Lo dejamos como constante aparte para poder reutilizarlo/testear el
# contenido exacto sin tener que bucear dentro del f-string gigante.
CONTRATO_GENERAR_PAYLOAD = """
CONTRATO ESTRICTO E INNEGOCIABLE de `generar_payload` (LÉELO CON CUIDADO,
la ronda anterior falló exactamente por violarlo):

   def generar_payload(comando: str) -> str

- El orquestador te llamará SIEMPRE con uno de estos strings EXACTOS, uno a
  la vez, tal cual, sin sufijos ni argumentos adicionales:
      "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"
- NO inventes variantes de la clave de entrada (nada de
  "TRANSFER_AC-0001_AC-0002_40000", ni "TRANSFER;AC-0001;...", ni tuplas,
  ni dicts por fuera). El parámetro `comando` es y será solo el nombre
  pelado del comando.
- Debes devolver un ÚNICO STRING (no dict, no tupla, no None) que sea un
  payload COMPLETO Y SINTÁCTICAMENTE VÁLIDO para ESE comando, con el mismo
  formato "CMD;arg1;arg2;...;control" que ves en los casos empíricos, listo
  para enviarse tal cual al servidor.
- El payload que generes debe apuntar a un CASO EXITOSO (status 200/201):
  usa cuentas y montos que, según tu propio modelo de estado acumulado,
  ya existan y sean válidos en ese punto de la sesión (p.ej. una cuenta
  creada antes con ALTA, un saldo suficiente para una TRANSFER u
  operación aún no anulada para ANULA). No generes a propósito un caso de
  error.
- Si `comando` es un valor que no reconoces, NUNCA devuelvas "" (string
  vacío) ni None: es preferible que devuelvas tu mejor intento de payload
  razonable para ese comando antes que un payload vacío o malformado — un
  payload vacío se cuenta SIEMPRE como un fallo automático de la prueba,
  sin excepción, así que no sirve como "salida segura".
- Antes de devolver el string, revisa tú mismo (dentro de la función, con
  un assert o una validación manual) que: (a) no está vacío, (b) empieza
  exactamente con el comando recibido seguido de ';', y (c) tiene al menos
  un campo de control no vacío al final. Si algo no cumple, corrige la
  construcción del payload en vez de devolver algo inválido.

PROHIBIDO CONFORMARTE CON MEMORIZAR: el orquestador llamará a
`generar_payload` VARIAS veces para el mismo comando a lo largo de la prueba
en vivo, y en cada llamada debe (cuando el comando lo permita) construir una
combinación DISTINTA a cualquier payload que ya viste literalmente en el
historial empírico — por ejemplo, un monto de DEPOSITO distinto a 250000,
700 o 100000, o una TRANSFER con una cantidad distinta a 40000/100000/50000
(siempre dentro de las reglas de negocio que dedujiste: saldo suficiente,
no superar el límite por operación, etc.). Devolver literalmente uno de los
20 payloads del dataset (copiado tal cual) es la SALIDA MÁS DÉBIL POSIBLE:
el orquestador la detecta y la cuenta aparte, porque reenviar un payload ya
visto no demuestra que entendiste el patrón — solo que sabes copiar texto.
Para que la prueba cuente como una confirmación real de tu hipótesis,
`generar_payload` debe ser capaz de sintetizar un control válido para una
BASE NUEVA (comando+argumentos que nunca aparecieron juntos en el
historial), usando la fórmula o el modelo que dedujiste para el control —
no un simple lookup de pares (base, control) ya vistos.
"""


def pedir_codigo_a_ia(casos_empiricos, pares_contraste, controles_confirmados, anulaciones_confirmadas, errores_previos=""):
    print(f"\n[🤖] Solicitando análisis y código al Genio Matemático (Modelo: {MODELO})...")

    casos_para_prompt = [
        {
            "n": c["n"],
            "payload": c["payload"],
            "status_real": c["status_real"],
        }
        for c in casos_empiricos
    ]

    texto_pares = formatear_pares_contraste(pares_contraste)
    validos, invalidos = controles_confirmados
    texto_controles = formatear_controles_confirmados(validos, invalidos)
    texto_anulaciones = formatear_anulaciones_confirmadas(anulaciones_confirmadas)

    prompt = f"""
Eres un AGENTE CIENTÍFICO Y CRIPTOANALISTA. Tienes un historial de peticiones a una
Caja Negra, EN EL ORDEN EXACTO en que ocurrieron (campo "n"):
{json.dumps(casos_para_prompt, indent=2)}

CONTROLES CONFIRMADOS (evidencia de ALTA prioridad, calculada automáticamente):
Para cada caso, si lo que falló (si falló algo) NO tuvo que ver con el
control, entonces el control de ESE caso era el CORRECTO para esa base —
aunque el caso haya fallado por otra razón (regla de negocio, cuenta
inexistente, etc). Esto te da muchos más puntos de referencia que solo mirar
los casos exitosos:
{texto_controles}

Usa estos pares como un problema de regresión: necesitas una función
f(base_string) -> control que reproduzca EXACTAMENTE todos los controles
"CORRECTOS" de la lista de arriba, y que NUNCA reproduzca ninguno de los
marcados "RECHAZADO". Antes de proponer una fórmula final, pruébala contra
TODOS estos pares en el sandbox (no solo un par) — una fórmula que solo
funciona para 1 o 2 ejemplos casi seguro es una coincidencia.

NOTA HONESTA: una búsqueda amplia de fórmulas simples (sumas ponderadas,
hashes polinómicos, CRC32, Adler32, DJB2, FNV-1a, SDBM, MD5/SHA1/SHA256,
sobre variantes en mayúsculas/minúsculas/solo-dígitos/solo-letras, con
módulos hasta 1000) NO encontró ninguna fórmula que explique todos estos
pares. Esto sugiere que:
(a) la fórmula usa una transformación distinta a las probadas (prueba otras:
    separar el string en sub-bloques y combinarlos con operaciones distintas,
    usar solo ciertos campos en vez del payload completo, usar el VALOR
    NUMÉRICO de los argumentos en vez de su representación ASCII, diferencias
    entre dígitos consecutivos, etc.), o
(b) el control depende de algo que NO está en el texto del payload (un
    contador de sesión, el número de petición "n", un estado previo). Si
    después de intentar variantes razonables no encuentras nada consistente,
    dilo explícitamente en tu análisis en vez de forzar una fórmula que solo
    funcione por coincidencia en 1-2 casos — es preferible que definas
    `simular_caja_negra` tratando el control como opaco (acéptalo tal cual
    viene en los payloads conocidos, y para los casos NO vistos usa tu mejor
    hipótesis) a que inventes una fórmula falsa que rompa todo lo demás.

PARES DE CONTRASTE DIRECTOS (mismo payload salvo el control, distinto resultado):
{texto_pares}

ANULACIONES CONFIRMADAS (evidencia de ALTA prioridad, calculada automáticamente):
{texto_anulaciones}

REGLA DE NEGOCIO CRÍTICA SOBRE ANULA (esto ha hecho fallar intentos anteriores
de forma sistemática, léelo con cuidado): cuando una operación (DEPOSITO,
TRANSFER, o cualquier comando que genere un "operacionId") es anulada con
éxito mediante ANULA (respuesta ok=true), su efecto sobre el estado NO debe
quedar solo "marcado como anulado" — debe REVERTIRSE de verdad. Por ejemplo,
si una TRANSFER movió dinero de una cuenta A a una cuenta B y luego esa
TRANSFER se anula, los saldos de A y B deben volver a como estaban ANTES de
esa transferencia, y todos los casos posteriores en la sesión (consultas de
saldo, nuevas transferencias que dependan de ese saldo, etc.) deben calcularse
sobre el saldo YA REVERTIDO, no sobre el saldo con el efecto todavía aplicado.
Si tu `simular_caja_negra` solo usa un diccionario de "operaciones anuladas"
para responder al propio ANULA pero no deshace el movimiento de saldo
correspondiente, vas a fallar casos posteriores que dependen de ese saldo
real — exactamente el patrón que debes evitar.

{errores_previos}

OBJETIVO DE ESTA FASE (no te pido más que esto todavía):
Debes ser capaz de predecir el STATUS HTTP correcto para cada payload, EN ORDEN.
Más adelante replicaremos también el cuerpo completo de la respuesta, pero por
ahora tu única métrica de éxito es el status.

CÓMO ANALIZAR (hazlo explícitamente, con texto, antes de escribir código):
1. Divide cada payload por ";" e identifica: comando, argumentos variables,
   y el campo final de control.
2. Usa los pares de contraste de arriba para aislar qué determina el
   resultado cuando solo cambia el control.
3. Identifica cuántos códigos de error distintos hay y en qué condición
   aparece cada uno (formato inválido vs. valor inválido vs. comando
   desconocido vs. aridad incorrecta vs. regla de negocio como límites o
   saldo, etc.). No asumas que son excluyentes: cuando un payload podría
   fallar por varias razones a la vez, usa el orden en que aparecen los
   casos para inferir qué validación se ejecuta primero.
4. PRESTA ESPECIAL ATENCIÓN a cualquier caso donde el status esperado sea de
   error (4xx/5xx) para un comando que en otros casos similares tuvo éxito:
   eso casi siempre significa una regla de negocio (p.ej. un monto máximo
   por operación, no solo saldo disponible) que es fácil pasar por alto si
   solo miras saldos. Compara los MONTOS involucrados en esos casos, no solo
   el control.
5. OJO: varios status dependen de ESTADO ACUMULADO (saldos que suben o bajan,
   contadores que avanzan, operaciones que ya fueron anuladas antes). No
   analices cada caso de forma aislada: analiza la secuencia completa como si
   fuera una sola sesión contra un servidor con memoria.
6. ANULA no es un simple interruptor: revisa la sección "ANULACIONES
   CONFIRMADAS" de arriba y, para cada una, verifica que tu simulador
   deshaga el efecto de saldo de la operación original a partir de ese punto
   de la sesión, no solo que recuerde que fue anulada.

ENTORNO DE EJECUCIÓN (SANDBOX):
Como eres un modelo de lenguaje, no puedes calcular hashes complejos o
módulos en tu "mente". Por lo tanto tienes un sandbox real.

1. MODO INVESTIGACIÓN: si aún no tienes claro el patrón del status (y
   especialmente si aún no sabes calcular el control exacto), escribe código
   Python que use print() para probar hipótesis: fuerza bruta sobre posibles
   fórmulas del control contra los pares de contraste de arriba, sumas de
   códigos ASCII con distintos pesos y módulos, etc. Todo lo que imprimas se
   te devolverá en el siguiente intento para que saques conclusiones. En
   este modo NO definas las funciones todavía.

2. MODO PRODUCCIÓN: cuando tengas una hipótesis sólida sobre el STATUS,
   define las DOS funciones obligatorias:

   def simular_caja_negra(payload: str) -> dict:
       # Debe devolver, como mínimo, {{"status": <int>}}. Si quieres ya
       # incluir otros campos de la respuesta no pasa nada, pero en esta
       # fase solo se evalúa "status".
       # IMPORTANTE: mantén el estado (cuentas, saldos, contadores,
       # operaciones anuladas, etc.) en variables a nivel de módulo, para
       # que llamadas sucesivas dentro de la misma ejecución reflejen el
       # efecto acumulado de las llamadas anteriores, igual que el backend
       # real.

{CONTRATO_GENERAR_PAYLOAD}

Reglas del código:
- Escribe ÚNICAMENTE UN bloque de código markdown (```python ... ```).
  Puedes escribir tu análisis como texto ANTES de ese bloque; no lo pongas
  dentro del bloque de código salvo como comentarios breves.
- Define toda función auxiliar dentro del código.
- Nunca uses ceros a la izquierda como literal numérico en Python
  (ej. escribe "0001" como string, nunca 0001, porque eso es un
  SyntaxError).
"""

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload_llm = {
        "model": MODELO,
        "messages": [{"role": "user", "content": prompt}]
    }

    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload_llm)
    if resp.status_code != 200:
        raise Exception(f"Error de OpenRouter: {resp.text}")

    cuerpo_respuesta = resp.json()["choices"][0]["message"]["content"].strip()

    bloques = re.findall(r"```(?:python)?(.*?)```", cuerpo_respuesta, flags=re.DOTALL | re.IGNORECASE)
    if bloques:
        codigo_limpio = "\n\n".join(b.strip() for b in bloques)
        print("\n[🧠] La IA razonó su respuesta. Código extraído con éxito.")
    else:
        codigo_limpio = cuerpo_respuesta.strip()

    return codigo_limpio


def probar_codigo_localmente(codigo_python, casos_empiricos):
    """Evalúa el código de la IA contra TODOS los casos, EN ORDEN.

    En esta fase solo se exige acertar el status de cada caso. Devuelve
    (exito, simular, generar, score, mensaje) donde score es la fracción de
    casos cuyo status se acertó (incluso si exito es False), para poder
    quedarnos con el mejor intento aunque no se llegue al 100%.
    """
    print("\n[🔬] Evaluando simulador localmente (Cuarentena)...")
    entorno_local = {}

    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()

    try:
        exec(codigo_python, entorno_local, entorno_local)
    except Exception as e:
        sys.stdout = old_stdout
        return False, None, None, 0.0, f"Tu código tuvo un error de ejecución/sintaxis: {str(e)}"
    finally:
        sys.stdout = old_stdout

    console_output = redirected_output.getvalue().strip()
    feedback_prints = f"\n[Salida de tus prints (STDOUT)]:\n{console_output}\n" if console_output else ""

    simular = entorno_local.get('simular_caja_negra')
    generar = entorno_local.get('generar_payload')

    if not simular or not generar:
        return False, None, None, 0.0, (
            f"Modo Investigación detectado. No encontré las funciones obligatorias. {feedback_prints}\n"
            "Usa estos datos para encontrar el patrón del status y define las funciones en tu próximo intento."
        )

    errores_encontrados = []
    aciertos = 0

    for caso in casos_empiricos:
        try:
            res_ia = simular(caso["payload"])
        except Exception as e:
            errores_encontrados.append(
                f"[caso n={caso['n']}] Payload '{caso['payload']}' -> Tu función crasheó: {str(e)}"
            )
            continue

        if not isinstance(res_ia, dict):
            errores_encontrados.append(
                f"[caso n={caso['n']}] Payload '{caso['payload']}' -> "
                f"simular_caja_negra no devolvió un dict (devolvió {type(res_ia).__name__})."
            )
            continue

        status_ia = res_ia.get("status")
        if status_ia != caso["status_real"]:
            clase_esperada = _clasificar_status(caso["status_real"])
            clase_obtenida = _clasificar_status(status_ia)
            if clase_esperada == "error" and clase_obtenida == "éxito":
                etiqueta = (
                    " [FALSO POSITIVO: tu código aceptó un payload que en realidad "
                    "debía fallar -> te falta una validación o regla de negocio]"
                )
            elif clase_esperada == "éxito" and clase_obtenida == "error":
                etiqueta = (
                    " [FALSO NEGATIVO: tu código rechazó un payload que en realidad "
                    "era válido -> alguna validación tuya es demasiado estricta o "
                    "está calculando mal el control]"
                )
            else:
                etiqueta = " [ambos son del mismo tipo (éxito/error) pero el código exacto no coincide]"
            errores_encontrados.append(
                f"[caso n={caso['n']}] Payload '{caso['payload']}' -> "
                f"Esperaba status {caso['status_real']}, tu simulador dio {status_ia}.{etiqueta}"
            )
        else:
            aciertos += 1

    total = len(casos_empiricos)
    score = aciertos / total if total else 0.0

    if errores_encontrados:
        resumen = "\n".join(errores_encontrados[:10])
        if len(errores_encontrados) > 10:
            resumen += f"\n... y otros {len(errores_encontrados) - 10} fallos más."
        return False, None, None, score, (
            f"Tu código acertó el status de {aciertos}/{total} casos ({score:.0%}).\n"
            "Recuerda: varios status dependen del ESTADO acumulado de la sesión "
            "(saldos, contadores, operaciones ya anuladas). Si tu simulador trata "
            "cada caso de forma aislada, probablemente ahí está el error.\n"
            f"Fallos detallados:\n{resumen}\n{feedback_prints}"
        )

    return True, simular, generar, score, (
        f"100% de los status acertados ({aciertos}/{total}).\n{feedback_prints}"
    )


def _validar_payload_generado(payload, comando_pedido):
    """Comprueba, ANTES de malgastar una llamada al servidor real, que lo
    que devolvió `generar_payload` es estructuralmente un payload válido
    para el comando pedido.

    Devuelve (es_valido, motivo_si_invalido). Esto es lo que bloquea el
    falso positivo original: un string vacío o mal formado nunca llega
    siquiera a enviarse, así que no puede "acertar por casualidad" un 400
    trivial de formato.
    """
    if payload is None or not isinstance(payload, str):
        return False, (
            f"generar_payload('{comando_pedido}') no devolvió un string "
            f"(devolvió {type(payload).__name__!r}: {payload!r})."
        )

    if payload.strip() == "":
        return False, (
            f"generar_payload('{comando_pedido}') devolvió un payload VACÍO. "
            "Un payload vacío no es una prueba válida de nada: el servidor lo "
            "rechaza trivialmente con 400 sin ni siquiera mirar tu hipótesis "
            "de control/estado, así que un '400 == 400' aquí es un falso "
            "positivo, no una confirmación."
        )

    partes = payload.split(";")
    if len(partes) < 2:
        return False, (
            f"generar_payload('{comando_pedido}') devolvió un payload mal "
            f"formado (sin los ';' esperados): '{payload}'."
        )

    if partes[0] != comando_pedido:
        return False, (
            f"generar_payload('{comando_pedido}') devolvió un payload cuyo "
            f"comando ('{partes[0]}') no coincide con el comando pedido "
            f"('{comando_pedido}'): '{payload}'."
        )

    control = partes[-1]
    if control.strip() == "":
        return False, (
            f"generar_payload('{comando_pedido}') devolvió un payload sin "
            f"campo de control (vacío al final): '{payload}'."
        )

    return True, None


def _es_payload_literal_conocido(payload, casos_base):
    """True si `payload` es, carácter por carácter, idéntico a uno de los
    payloads que ya aparecían en el historial empírico.

    Esto existe porque `generar_payload` puede "hacer trampa de forma
    sutil": en vez de sintetizar un payload nuevo a partir de su hipótesis
    (control, reglas de negocio, estado), simplemente devuelve uno de los
    20 payloads conocidos tal cual. Esa salida SIEMPRE va a coincidir con
    el servidor real (porque ya sabemos que es correcta de antemano), así
    que por sí sola no prueba que el modelo generaliza — solo que memorizó
    texto. La usamos para no confundir "memorización" con "confirmación".
    """
    conocidos = {c["payload"] for c in casos_base}
    return payload in conocidos


def _es_400_trivial_de_formato(status_real, respuesta_real):
    """Detecta si un 400 del servidor real es el eco trivial de un payload
    vacío/mal formado (el mismo tipo de error que E201/E202 en el dataset:
    'control mal formado', payload vacío, etc.) en vez de una respuesta de
    negocio genuina. Esto es una segunda red de seguridad por si el payload
    pasó la validación estructural pero igual resultó en un rechazo de
    formato puro en el servidor real.
    """
    if status_real != 400:
        return False
    mensaje = (respuesta_real.get("mensaje") or "").lower()
    return "mal formado" in mensaje or "vacío" in mensaje or "vacio" in mensaje


def prueba_quirurgica_real(simular, generar, casos_base):
    print("\n[🚀] INICIANDO PRUEBA QUIRÚRGICA EN SERVIDOR REAL...")
    cliente = Cliente()

    # --- PREPARACIÓN DEL ESTADO ---
    # El servidor real inicia en blanco (0 cuentas, 0 operaciones).
    # Para que las pruebas de estado (como TRANSFER, ANULA, DEPOSITO) funcionen y 
    # coincidan con lo que tu código simuló localmente, debemos replicar TODA la 
    # historia empírica en el servidor real para sincronizar su base de datos interna.
    print("[*] (Preparación) Replicando historial empírico en servidor real para sincronizar estado...")
    for caso in casos_base:
        # Enviamos los payloads conocidos para poblar cuentas, saldos y operaciones previas
        cliente.msg(caso["payload"], seq="sync_state", hipotesis="sincronizacion_estado_previo")

    comandos = COMANDOS_PROBABLES_EN_VIVO
    huno_algun_exito_2xx = False
    huno_algun_exito_2xx_novedoso = False
    payloads_vistos_en_esta_prueba = set()

    def _ejecutar_una_prueba(cmd, etiqueta_prueba):
        """Genera, valida, simula y envía un payload para `cmd`. Devuelve
        (ok, mensaje_si_fallo, fue_2xx, fue_novedoso)."""
        try:
            payload = generar(cmd)
        except Exception as e:
            return False, (
                f"La {etiqueta_prueba} fracasó: generar_payload('{cmd}') lanzó una "
                f"excepción: {str(e)}"
            ), False, False

        # --- BARRERA 1: validar el payload ANTES de tocar el servidor ---
        es_valido, motivo = _validar_payload_generado(payload, cmd)
        if not es_valido:
            return False, f"La {etiqueta_prueba} fracasó. {motivo}", False, False

        # ¿Es un payload genuinamente nuevo, o un simple copy-paste de algo
        # ya visto en el dataset empírico (o repetido dentro de esta misma
        # prueba quirúrgica)? Esto NO bloquea el envío —un payload conocido
        # sigue siendo útil como señal de que el status básico cuadra— pero
        # se usa más abajo para decidir si la prueba demuestra generalización
        # real o solo memorización.
        es_copia_conocida = _es_payload_literal_conocido(payload, casos_base)
        es_repetido_en_sesion = payload in payloads_vistos_en_esta_prueba
        payloads_vistos_en_esta_prueba.add(payload)
        fue_novedoso = not es_copia_conocida and not es_repetido_en_sesion

        try:
            etiqueta_novedad = "NUEVO" if fue_novedoso else "ya conocido/repetido"
            print(f"\n[*] ({etiqueta_prueba}, payload {etiqueta_novedad}) Enviando: '{payload}'")
            estimacion = simular(payload)
        except Exception as e:
            return False, (
                f"La {etiqueta_prueba} fracasó: simular_caja_negra('{payload}') lanzó "
                f"una excepción: {str(e)}"
            ), False, fue_novedoso

        if not isinstance(estimacion, dict) or "status" not in estimacion:
            return False, (
                f"La {etiqueta_prueba} fracasó: simular_caja_negra('{payload}') no "
                f"devolvió un dict con 'status' (devolvió {estimacion!r})."
            ), False, fue_novedoso

        fila_log = cliente.msg(payload, seq=f"prueba_quirurgica_{etiqueta_prueba}", hipotesis="Validando estimacion de status")
        status_real = fila_log["status"]
        respuesta_real = fila_log.get("response", {}) or {}
        error_real = respuesta_real.get("error")

        print(f"    -> Simulador estimó status: {estimacion.get('status')}")
        print(f"    -> Servidor real dio: Status {status_real}, Error: {error_real}")

        # --- BARRERA 2: no dejar pasar un 400 que sea el eco trivial de
        # formato aunque el payload haya superado la barrera 1 ---
        if _es_400_trivial_de_formato(status_real, respuesta_real):
            return False, (
                f"La {etiqueta_prueba} fracasó. Payload: '{payload}'. El servidor "
                f"real lo rechazó con un 400 de FORMATO trivial (error: {error_real}), "
                "no con una respuesta de negocio real. Esto no demuestra que tu "
                "hipótesis de status sea correcta; genera un payload realmente "
                "válido."
            ), False, fue_novedoso

        if status_real != estimacion.get("status"):
            return False, (
                f"La {etiqueta_prueba} fracasó. Payload: '{payload}'. "
                f"Estimamos status {estimacion.get('status')}, Servidor real: {status_real}. "
                f"Error real: {error_real}. Replantea tu hipótesis del status."
            ), False, fue_novedoso

        return True, None, _clasificar_status(status_real) == "éxito", fue_novedoso

    cmd_1 = random.choice(comandos)
    ok, msj, fue_2xx, fue_novedoso = _ejecutar_una_prueba(cmd_1, "1ra prueba")
    if not ok:
        return False, msj
    huno_algun_exito_2xx = huno_algun_exito_2xx or fue_2xx
    huno_algun_exito_2xx_novedoso = huno_algun_exito_2xx_novedoso or (fue_2xx and fue_novedoso)

    print("\n[+] Primera prueba EXITOSA. Lanzando 3 peticiones cruzadas adicionales...")

    # Usamos 3 confirmaciones en vez de 2: con solo 2 era demasiado fácil
    # que las 3 pruebas en total terminaran siendo puro copy-paste del
    # dataset. Más intentos dan más oportunidades de que generar_payload
    # se vea forzado a sintetizar algo nuevo para distintos comandos.
    confirmaciones = [random.choice(comandos) for _ in range(3)]
    for i, cmd in enumerate(confirmaciones):
        ok, msj, fue_2xx, fue_novedoso = _ejecutar_una_prueba(cmd, f"confirmación {i + 2}")
        if not ok:
            return False, msj
        huno_algun_exito_2xx = huno_algun_exito_2xx or fue_2xx
        huno_algun_exito_2xx_novedoso = huno_algun_exito_2xx_novedoso or (fue_2xx and fue_novedoso)

    if not huno_algun_exito_2xx:
        # No es un fallo duro (todos los payloads eran válidos y los status
        # se acertaron), pero avisamos con fuerza: si nunca se acertó un
        # caso realmente exitoso (200/201), la prueba solo demostró que la
        # IA sabe replicar rechazos, no que sepa forjar un payload que el
        # servidor acepte de verdad.
        print(
            "\n[⚠️] Las pruebas acertaron su status, pero NINGUNA fue un "
            "200/201 real. La confirmación es débil: no se demostró que la "
            "IA pueda forjar un payload exitoso de verdad."
        )
        return False, (
            "Las pruebas en vivo acertaron el status, pero todas fueron "
            "casos de ERROR (ningún 200/201). Eso no prueba que sepas forjar "
            "un payload realmente válido y aceptado por el servidor. Ajusta "
            "generar_payload para apuntar deliberadamente a un caso exitoso "
            "conocido (cuenta existente, saldo suficiente, operación aún no "
            "anulada, etc.) en vez de conformarte con reproducir un rechazo."
        )

    if not huno_algun_exito_2xx_novedoso:
        # Este es el caso que motivó este cambio: todos los 200/201
        # conseguidos fueron simplemente payloads copiados tal cual del
        # dataset empírico (o repetidos entre sí). Eso confirma que el
        # status básico de esos casos puntuales es correcto, pero NO
        # confirma que la hipótesis generaliza a combinaciones nuevas que
        # sigan el mismo patrón — que es justamente lo que se quiere probar
        # antes de dar la hipótesis por buena.
        print(
            "\n[⚠️] Hubo éxitos 2xx, pero TODOS fueron payloads ya conocidos "
            "(copiados del dataset) o repetidos entre sí. No se demostró "
            "generalización real."
        )
        return False, (
            "Se consiguieron respuestas 2xx reales, pero en todos los casos "
            "generar_payload simplemente reenvió un payload YA CONOCIDO del "
            "dataset empírico (o repitió el mismo payload varias veces) en "
            "vez de sintetizar una combinación NUEVA (otro monto, otra "
            "cuenta) que siga el patrón deducido. Reenviar texto memorizado "
            "siempre va a coincidir con el servidor, así que no prueba nada "
            "sobre tu hipótesis. Ajusta generar_payload para construir, a "
            "partir de tu modelo de control y de estado, un payload "
            "genuinamente nuevo que nunca apareció tal cual en el historial, "
            "y que aun así el servidor acepte como 200/201."
        )

    return True, (
        "¡Los status de todas las pruebas coincidieron con el servidor real, "
        "incluyendo al menos un 200/201 genuinamente NUEVO (no copiado del "
        "dataset)! Esto confirma que la hipótesis generaliza, no solo que "
        "memorizó los casos conocidos."
    )


def main():
    if not OPENROUTER_API_KEY:
        print("[!] ERROR: No se encontró OPENROUTER_API_KEY.")
        return

    casos_base = cargar_casos_empiricos(RUTA_DATASET)
    print(f"[*] CARGADOS {len(casos_base)} CASOS EMPÍRICOS (fase actual: acertar STATUS HTTP).")

    pares_contraste = detectar_pares_contraste(casos_base)
    controles_confirmados = extraer_controles_confirmados(casos_base)
    anulaciones_confirmadas = extraer_anulaciones_confirmadas(casos_base)
    print(f"[*] Pares de contraste detectados automáticamente: {len(pares_contraste)}")
    print(f"[*] Controles confirmados: {len(controles_confirmados[0])} válidos, {len(controles_confirmados[1])} inválidos")
    print(f"[*] Anulaciones exitosas detectadas automáticamente: {len(anulaciones_confirmadas)}")

    intentos = 0
    errores_historial = ""
    mejor_intento = {"score": -1.0, "codigo": None}

    while intentos < MAX_INTENTOS:
        intentos += 1
        print(f"\n=== BUCLE DE ESTIMACIÓN Y CHOQUE: INTENTO {intentos} ===")

        try:
            codigo = pedir_codigo_a_ia(casos_base, pares_contraste, controles_confirmados, anulaciones_confirmadas, errores_historial)
        except Exception as e:
            # Error de infraestructura (red, API caída, etc.): no tiene que
            # ver con la lógica de la IA, así que no gastamos esto como un
            # "fallo lógico" ni abortamos el programa entero.
            print(f"[!] Error de infraestructura consultando al modelo: {e}. Reintentando...")
            continue

        exito_local, simular, generar, score, msj_local = probar_codigo_localmente(codigo, casos_base)

        if score > mejor_intento["score"]:
            mejor_intento = {"score": score, "codigo": codigo}

        if not exito_local:
            print(f"[❌] Falló asimilación empírica local:\n    -> {msj_local}")
            errores_historial = (
                f"\n=== TU ÚLTIMO INTENTO (resultado: {score:.0%} de status acertados) ===\n"
                f"Escribiste este código:\n```python\n{codigo}\n```\n"
                f"Resultado:\n{msj_local}\n"
                "Usa esto para mejorar tu deducción en el próximo intento.\n"
            )
            continue

        print(f"[✅] {msj_local}")
        exito_real, msj_real = prueba_quirurgica_real(simular, generar, casos_base)

        if exito_real:
            print(f"\n[🎉] ¡HIPÓTESIS DE STATUS CONFIRMADA POR EL SERVIDOR!\n{msj_real}")
            print("\n[Código Final Desplegable]:\n" + codigo)
            return

        print(f"\n[❌] Rechazado por servidor real:\n    -> {msj_real}")
        errores_historial = (
            f"\n=== TU ÚLTIMO INTENTO (100% local, pero falló en servidor real) ===\n"
            f"Escribiste este código:\n```python\n{codigo}\n```\n"
            f"Fallaste en el servidor real: {msj_real}\n"
            "Corrige tu lógica del status.\n"
        )

    print(f"\n[⚠️] Se agotaron los {MAX_INTENTOS} intentos sin una réplica perfecta confirmada.")
    if mejor_intento["codigo"] is not None:
        print(f"[*] Mejor resultado local obtenido: {mejor_intento['score']:.0%} de status acertados.")
        print("\n[Código del mejor intento (no confirmado en servidor real)]:\n" + mejor_intento["codigo"])
    else:
        print("[*] Ningún intento llegó siquiera a definir las funciones requeridas.")


if __name__ == "__main__":
    main()