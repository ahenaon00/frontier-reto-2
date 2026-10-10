"""Descubrimiento de patrones de la caja negra (reinicio de enfoque).

Este script NO intenta adivinar el servicio: lo OBSERVA. El proceso es:

  FASE 1 -- REPLAY
    Se releen los 20 ejemplos de `pruebas/ejemplos.jsonl` (grabados con la
    versión de la mañana) y se reenvían al servicio ORIGINAL, tras un
    `POST /__reset`, en el mismo orden. Se compara cada respuesta observada
    con la grabada. Así sabemos qué cambió hoy con respecto a los ejemplos.

  FASE 2 -- ESTRUCTURA
    Solo con los datos (y el replay), se extrae la estructura fundamental:
    qué comandos existen, cuántos argumentos recibe cada uno, qué errores hay
    con su status y mensaje exactos, en qué orden parecen evaluarse, y qué
    controles fueron aceptados/rechazados por base.

  FASE 3 -- SONDEO (opcional, controlado por presupuesto)
    Se asume un patrón (hipótesis), se traducen esas hipótesis en requests
    NUEVAS y se envían al original. Se comparan con lo que la hipótesis
    predecía. Toda respuesta con un código/mensaje relevante se acumula.

  Todo hallazgo se acumula en:
    - `patrones_encontrados.jsonl`  (registro rico, con hipótesis y conclusión)
    - `patrones_encontrados.md`     (resumen legible)
    - `pruebas/ejemplos_nuevos.jsonl` (formato idéntico a ejemplos.jsonl, para
      ampliar el dataset que alimenta al modelo)

Se mantienen prints de prueba a lo largo de todo el proceso.
"""

import json
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from explorador.cliente import Cliente

# ----------------------------------------------------------------------------
# Rutas y configuración
# ----------------------------------------------------------------------------
RAIZ = os.path.dirname(os.path.abspath(__file__))
EJEMPLOS = os.path.join(RAIZ, "pruebas", "ejemplos.jsonl")
PATRONES_JSONL = os.path.join(RAIZ, "patrones_encontrados.jsonl")
PATRONES_MD = os.path.join(RAIZ, "patrones_encontrados.md")
EJEMPLOS_NUEVOS = os.path.join(RAIZ, "pruebas", "ejemplos_nuevos.jsonl")

# Tope de requests que este script puede gastar en la fase de sondeo. Es un
# seguro: el token admite 8.000/día. El replay de los 20 ejemplos no cuenta
# contra este tope (es obligatorio para comparar).
PRESUPUESTO_SONDEO = int(os.environ.get("PRESUPUESTO_SONDEO", "0"))
# REPLAY=0 permite iterar en las sondas sin volver a reenviar los 20 ejemplos
# (evita duplicar el replay en patrones_encontrados.jsonl). La estructura se
# calcula entonces con los datos grabados.
HACER_REPLAY = os.environ.get("REPLAY", "1") != "0"


# ----------------------------------------------------------------------------
# Comparación de respuestas (mismas reglas que el juez del reto)
# ----------------------------------------------------------------------------
def cuerpos_iguales(a, b):
    """Compara dos cuerpos con las reglas del reto:
    - objetos JSON: las claves pueden venir en cualquier orden.
    - arrays: mismo orden.
    - strings y números: idénticos (0 no es 0.0).
    - si alguno no es JSON: texto exacto.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(cuerpos_iguales(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(cuerpos_iguales(x, y) for x, y in zip(a, b))
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a == b


# ----------------------------------------------------------------------------
# Acumulador persistente de patrones
# ----------------------------------------------------------------------------
class RegistroPatrones:
    """Escribe hallazgos en `patrones_encontrados.jsonl` y, además, guarda las
    respuestas nuevas en formato `ejemplos.jsonl` para ampliar el dataset."""

    def __init__(self):
        self.jsonl = open(PATRONES_JSONL, "a", encoding="utf-8")
        self.nuevos = open(EJEMPLOS_NUEVOS, "a", encoding="utf-8")
        self.contador = 0
        self._siguiente_n = self._max_n_ejemplos_nuevos() + 1

    def _max_n_ejemplos_nuevos(self):
        if not os.path.exists(EJEMPLOS_NUEVOS):
            return 0
        n = 0
        with open(EJEMPLOS_NUEVOS, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    n = max(n, json.loads(linea).get("n", 0))
        return n

    def nuevo_ejemplo(self, request, status, response, seq, hipotesis):
        """Guarda una respuesta nueva con el MISMO formato que ejemplos.jsonl."""
        fila = {
            "n": self._siguiente_n,
            "id": self._siguiente_n,
            "seq": seq,
            "request": request,
            "status": status,
            "response": response,
            "hipotesis": hipotesis,
            "capturado_en": int(time.time()),
        }
        self._siguiente_n += 1
        self.nuevos.write(json.dumps(fila, ensure_ascii=False) + "\n")
        self.nuevos.flush()
        return fila

    def hallazgo(self, tipo, payload, observado, prediccion=None,
                 coincide=None, conclusion=None, extra=None):
        """Registra un hallazgo (replay, sonda, patrón estructural...)."""
        self.contador += 1
        fila = {
            "id": self.contador,
            "tipo": tipo,
            "ts": int(time.time()),
            "request": {"m": payload} if isinstance(payload, str) else payload,
            "observado": observado,
        }
        if prediccion is not None:
            fila["prediccion"] = prediccion
        if coincide is not None:
            fila["coincide"] = coincide
        if conclusion:
            fila["conclusion"] = conclusion
        if extra:
            fila["extra"] = extra
        self.jsonl.write(json.dumps(fila, ensure_ascii=False) + "\n")
        self.jsonl.flush()
        return fila

    def cerrar(self):
        self.jsonl.close()
        self.nuevos.close()


# ----------------------------------------------------------------------------
# Utilidades de parseo
# ----------------------------------------------------------------------------
def cargar_ejemplos(ruta=EJEMPLOS):
    casos = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            d = json.loads(linea)
            casos.append({
                "n": d.get("n"),
                "payload": d["request"]["m"],
                "status": d["status"],
                "response": d.get("response", {}),
            })
    casos.sort(key=lambda c: c["n"] if c["n"] is not None else 0)
    return casos


def separar_payload(payload):
    """Separa comando, argumentos y control. El control es el último campo."""
    partes = payload.split(";")
    comando = partes[0].strip() if partes else ""
    args = partes[1:]
    control = args[-1] if args else None
    return comando, args, control, partes


# ----------------------------------------------------------------------------
# FASE 1 -- Replay de los ejemplos contra el original
# ----------------------------------------------------------------------------
def fase_replay(casos, cliente, registro):
    print("\n" + "=" * 78)
    print("FASE 1 -- REPLAY DE LOS EJEMPLOS CONTRA EL SERVICIO ORIGINAL")
    print("=" * 78)

    try:
        cliente.reset()
        print("[*] POST /__reset -> estado inicial restaurado.")
    except Exception as e:
        print(f"[!] No se pudo hacer reset: {e}")
        return []

    print(f"[*] Reenviando {len(casos)} requests en orden...\n")
    resultados = []
    for c in casos:
        fila = cliente.msg(
            c["payload"],
            seq="descubrimiento_replay",
            hipotesis=f"replay del ejemplo n={c['n']} para ver si la version vigente responde igual",
        )
        obs_status = fila["status"]
        obs_body = fila["response"]

        estatus_ok = (obs_status == c["status"])
        cuerpo_ok = cuerpos_iguales(obs_body, c["response"])
        coincide = estatus_ok and cuerpo_ok

        marca = "OK " if coincide else "DIF"
        print(f"[{marca}] n={c['n']:>2} '{c['payload']}'")
        if not coincide:
            print(f"        esperado: {c['status']} {json.dumps(c['response'], ensure_ascii=False)}")
            print(f"        observado: {obs_status} {json.dumps(obs_body, ensure_ascii=False)}")

        registro.hallazgo(
            tipo="replay",
            payload=c["payload"],
            observado={"status": obs_status, "body": obs_body},
            prediccion={"status": c["status"], "body": c["response"]},
            coincide=coincide,
            conclusion=(
                "la version vigente responde igual al ejemplo grabado"
                if coincide else
                "la version vigente CAMBIO con respecto al ejemplo grabado"
            ),
            extra={"n": c["n"], "x_req": fila.get("x_req")},
        )

        resultados.append({
            "n": c["n"], "payload": c["payload"],
            "esperado_status": c["status"], "esperado_body": c["response"],
            "obs_status": obs_status, "obs_body": obs_body,
            "coincide": coincide,
        })

    iguales = sum(1 for r in resultados if r["coincide"])
    print("\n" + "-" * 78)
    print(f"[RESUMEN REPLAY] {iguales}/{len(resultados)} respuestas siguen siendo idénticas.")
    if iguales < len(resultados):
        print(f"[!] {len(resultados) - iguales} respuestas cambiaron -> el servicio evolucionó desde la mañana.")
    print("-" * 78)
    return resultados


# ----------------------------------------------------------------------------
# FASE 2 -- Estructura fundamental extraída de los datos
# ----------------------------------------------------------------------------
def fase_estructura(casos, resultados, registro):
    print("\n" + "=" * 78)
    print("FASE 2 -- ESTRUCTURA FUNDAMENTAL (solo a partir de los datos)")
    print("=" * 78)

    comandos = {}
    errores = {}
    controles_ok = {}
    controles_bad = {}
    controles_ambiguos = []

    # Trabajamos con lo OBSERVADO hoy (el replay); si no hubo replay (REPLAY=0
    # o fallo de red), caemos en los datos grabados de ejemplos.jsonl.
    if resultados:
        base_datos = resultados
    else:
        print("[*] (REPLAY desactivado: estructura sobre los datos grabados)")
        base_datos = [
            {"payload": c["payload"], "obs_status": c["status"], "obs_body": c["response"]}
            for c in casos
        ]

    for r in base_datos:
        payload = r["payload"]
        status = r["obs_status"]
        body = r["obs_body"]
        comando, args, control, _ = separar_payload(payload)
        comando_norm = comando.upper()

        info = comandos.setdefault(comando_norm, {"n_args": set(), "ejemplos": []})
        # n_args = nº de argumentos SIN contar el control
        info["n_args"].add(len(args) - 1 if args else 0)
        info["ejemplos"].append({"payload": payload, "status": status, "body": body})

        if isinstance(body, dict) and body.get("error"):
            cod = body["error"]
            e = errores.setdefault(cod, {
                "status": status, "mensaje": body.get("mensaje"), "n": 0,
                "condiciones": [],
            })
            e["n"] += 1
            e["condiciones"].append(payload)

        # Control aceptado/rechazado SOLO cuando los datos lo confirman.
        # Un error ESTRUCTURAL (aridad, comando desconocido) no confirma nada:
        # es posible que se evalúe antes que el control y este nunca se evalúe.
        if args:
            clave = ";".join(payload.split(";")[:-1])
            mensaje = (body.get("mensaje") or "").lower() if isinstance(body, dict) else ""
            if "control" in mensaje:
                if "mal formado" in mensaje or "formato" in mensaje:
                    pass  # ni siquiera parece un número: no aporta nada
                else:
                    controles_bad[(clave, control)] = True
            elif "aridad" in mensaje or "desconocid" in mensaje:
                controles_ambiguos.append((clave, control, status, mensaje))
            else:
                controles_ok[(clave, control)] = True

    # --- Imprimir comandos y aridades
    print("\n[COMANDOS DETECTADOS]")
    for cmd in sorted(comandos):
        info = comandos[cmd]
        n_args = sorted(info["n_args"])
        print(f"  - {cmd}: aridad observada (args sin control) = {n_args}")

    # --- Imprimir errores
    print("\n[ERRORES DETECTADOS]")
    for cod in sorted(errores):
        e = errores[cod]
        print(f"  - {cod}: status {e['status']} | mensaje {e['mensaje']!r} | visto {e['n']}x")

    # --- Imprimir controles
    print("\n[CONTROLES]")
    print("  Aceptados (negocio/éxito):")
    for (clave, control) in sorted(controles_ok):
        print(f"    '{clave}' -> {control}")
    print("  Rechazados (control inválido):")
    for (clave, control) in sorted(controles_bad):
        print(f"    '{clave}' -> {control}")
    print("  NO concluyentes (falló antes del control: aridad / comando desconocido):")
    for (clave, control, status, _) in sorted(controles_ambiguos):
        print(f"    '{clave}' -> {control}  (status {status})")

    # --- Persistir hallazgos estructurales
    registro.hallazgo(
        tipo="estructura",
        payload="<resumen>",
        observado={
            "comandos": {c: sorted(i["n_args"]) for c, i in comandos.items()},
            "errores": {c: {"status": e["status"], "mensaje": e["mensaje"]}
                        for c, e in errores.items()},
            "controles_aceptados": [f"{k}->{v}" for k, v in controles_ok],
            "controles_rechazados": [f"{k}->{v}" for k, v in controles_bad],
            "controles_no_concluyentes": [f"{k}->{v}" for k, v, _, _ in controles_ambiguos],
        },
        conclusion="estructura fundamental inferida de los datos observados",
    )

    print("\n[*] Estructura guardada en patrones_encontrados.jsonl")
    return {"comandos": comandos, "errores": errores,
            "controles_ok": controles_ok, "controles_bad": controles_bad,
            "controles_ambiguos": controles_ambiguos}


# ----------------------------------------------------------------------------
# FASE 3 -- Sondeo de hipótesis contra el original (controlado)
# ----------------------------------------------------------------------------
def _rechaza_control(status, body):
    """True si la respuesta dice que el CONTROL fue rechazado (no por formato)."""
    if not isinstance(body, dict):
        return False
    mensaje = (body.get("mensaje") or "").lower()
    if "control" not in mensaje:
        return False
    if "mal formado" in mensaje or "formato" in mensaje:
        return False
    return True


def fase_sondeo(estructura, cliente, registro):
    """Envía requests NUEVAS para comprobar hipótesis y descubrir patrones.

    Se controla con variables de entorno:
      - PRESUPUESTO_SONDEO: tope total de requests que puede gastar esta fase.
        Si es 0 (por defecto) no se envía nada.
      - SWEEP_BASES: bases (separadas con '|') cuyo control se quiere
        descubrir, p. ej. SWEEP_BASES="CONSULTA;AC-0030|CONSULTA;AC-0031".
        Para cada base se prueban los controles 00..97 hasta hallar el aceptado.
      - SWEEP_RANGO: cuántos controles probar por base (por defecto 98).
    """
    print("\n" + "=" * 78)
    print("FASE 3 -- SONDEO DE HIPÓTESIS CONTRA EL ORIGINAL")
    print("=" * 78)

    if PRESUPUESTO_SONDEO <= 0:
        print("[*] PRESUPUESTO_SONDEO=0 -> fase de sondeo desactivada.")
        print("    Ejecuta con, p. ej.:  PRESUPUESTO_SONDEO=200 python3 descubrimiento.py")
        return

    print(f"[*] Presupuesto de sondeo: {PRESUPUESTO_SONDEO} requests.\n")
    estado = {"gastado": 0, "tope": PRESUPUESTO_SONDEO}
    # Permite elegir qué experimentos correr: SONDAS=integridad,aridad,sweep
    activas = set(os.environ.get("SONDAS", "integridad,aridad,sweep").split(","))

    def sonda(payload, hipotesis, prediccion=None, seq="sonda",
              guardar=True, silencioso=False):
        if estado["gastado"] >= estado["tope"]:
            return None
        fila = cliente.msg(payload, seq=seq, hipotesis=hipotesis)
        estado["gastado"] += 1
        obs = {"status": fila["status"], "body": fila["response"]}
        coincide = None
        if prediccion is not None:
            coincide = (prediccion["status"] == obs["status"] and
                        cuerpos_iguales(prediccion.get("body"), obs["body"]))
            if not silencioso:
                marca = f"  (predicción {'OK' if coincide else 'FALLA'})"
                print(f"[SONDA] '{payload}' -> {obs['status']} "
                      f"{json.dumps(obs['body'], ensure_ascii=False)}{marca}")
        elif not silencioso:
            print(f"[SONDA] '{payload}' -> {obs['status']} "
                  f"{json.dumps(obs['body'], ensure_ascii=False)}")
        registro.hallazgo(
            tipo="sonda", payload=payload, observado=obs,
            prediccion=prediccion, coincide=coincide,
            conclusion=hipotesis, extra={"x_req": fila.get("x_req")},
        )
        if guardar:
            registro.nuevo_ejemplo({"m": payload}, obs["status"], obs["body"],
                                   seq=seq, hipotesis=hipotesis)
        return obs

    def reset():
        if estado["gastado"] >= estado["tope"]:
            return
        cliente.reset()

    def descubrir_control(base, rango):
        """Prueba 0..rango-1 para 'base'; registra el primer control aceptado.

        OJO: el control se escribe SIN ceros a la izquierda (es el número en
        decimal natural): 'CONSULTA;AC-0003;8' es válido, '...;08' no.
        """
        intentos = 0
        for cc in range(rango):
            payload = f"{base};{cc}"
            obs = sonda(payload, f"¿acepta el control {cc:02d} para '{base}'?",
                        seq="sweep_control", guardar=False, silencioso=True)
            if obs is None:
                break  # presupuesto agotado
            intentos += 1
            if not _rechaza_control(obs["status"], obs["body"]):
                registro.hallazgo(
                    tipo="control_aceptado", payload=payload, observado=obs,
                    conclusion=f"control aceptado para la base '{base}'",
                    extra={"base": base, "control": cc},
                )
                registro.nuevo_ejemplo({"m": payload}, obs["status"], obs["body"],
                                       seq="sweep_control",
                                       hipotesis=f"control aceptado para '{base}'")
                print(f"  [CONTROL] '{base}' -> {cc} (aceptado tras {intentos} intentos)")
                return [cc]
        registro.hallazgo(
            tipo="control_no_hallado", payload=f"{base};*",
            observado={"intentos": intentos},
            conclusion=f"no se halló control aceptado para '{base}' en 0..{rango-1}",
            extra={"base": base},
        )
        print(f"  [CONTROL] '{base}' -> NO hallado en {intentos} intentos")
        return []

    # --- Experimento A: integridad del mensaje (sin estado) -----------------
    if "integridad" in activas:
        print("\n[A] INTEGRIDAD: forma del payload y del control")
        probes_integridad = [
            ("PING", "PING sin control: ¿cómo se valida la forma?"),
            ("PING;", "PING con control vacío"),
            ("PING;64", "PING con control correcto (baseline)"),
            ("PING;00", "PING con OTRO control: ¿importa el control en PING?"),
            ("PING;xx", "control no numérico"),
            ("PING;999", "control de 3 dígitos"),
            ("ping;64", "comando en minúsculas"),
            ("PiNg;64", "comando con mayúsculas mezcladas"),
            ("PING;64 ", "espacio al final del control"),
            (" PING;64", "espacio al inicio del payload"),
            ("PING;64;extra", "campo extra después del control"),
            ("FOO;64", "comando desconocido"),
            ("foo;64", "comando desconocido en minúsculas"),
            ("", "payload vacío"),
            (";", "solo separador"),
        ]
        for payload, hip in probes_integridad:
            sonda(payload, hip, seq="sonda_integridad")

    # --- Experimento B: aridad por comando (control '00') -------------------
    # Si la aridad se valida ANTES que el control, veremos E302; si no, E202.
    # Esto revela el ORDEN de validación, parte clave de la especificación.
    if "aridad" in activas:
        print("\n[B] ARIDAD POR COMANDO (usando control '00'): orden aridad vs control")
        reset()
        for cmd in ["PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"]:
            for n_args in range(0, 5):
                args = [f"A{i}" for i in range(n_args)]
                payload = ";".join([cmd] + args + ["00"])
                sonda(payload, f"{cmd} con {n_args} argumentos + control '00'",
                      seq="sonda_aridad")

    # --- Experimento C: barridos de control (si se configuraron) ------------
    bases_sweep = [b for b in os.environ.get("SWEEP_BASES", "").split("|") if b.strip()]
    if "sweep" not in activas:
        bases_sweep = []
    if bases_sweep:
        rango = int(os.environ.get("SWEEP_RANGO", "98"))
        print(f"\n[C] BARRIDOS DE CONTROL sobre {len(bases_sweep)} bases "
              f"(0..{rango - 1}, sin ceros a la izquierda, parando al aceptarlo)")
        reset()
        for base in bases_sweep:
            descubrir_control(base, rango)
    else:
        print("\n[C] BARRIDOS DE CONTROL: desactivados (define SWEEP_BASES).")

    print(f"\n[*] Sondas enviadas en esta fase: {estado['gastado']}/{estado['tope']}")


# ----------------------------------------------------------------------------
# Resumen legible
# ----------------------------------------------------------------------------
def escribir_resumen_md(casos, resultados):
    iguales = sum(1 for r in resultados if r["coincide"]) if resultados else 0
    total = len(resultados)
    with open(PATRONES_MD, "w", encoding="utf-8") as f:
        f.write("# Patrones encontrados\n\n")
        f.write(f"- Fecha de captura: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- Ejemplos re-verificados: {total}\n")
        f.write(f"- Respuestas que siguen idénticas: {iguales}/{total}\n\n")
        f.write("## Detalle del replay\n\n")
        f.write("| n | payload | esperado | observado | ¿coincide? |\n")
        f.write("|---|---------|----------|-----------|-------------|\n")
        for r in resultados:
            f.write(
                f"| {r['n']} | `{r['payload']}` | {r['esperado_status']} "
                f"{json.dumps(r['esperado_body'], ensure_ascii=False)} | "
                f"{r['obs_status']} {json.dumps(r['obs_body'], ensure_ascii=False)} | "
                f"{'sí' if r['coincide'] else '**no**'} |\n"
            )
    print(f"\n[*] Resumen legible escrito en {os.path.relpath(PATRONES_MD, RAIZ)}")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    print("=" * 78)
    print("DESCUBRIMIENTO DE PATRONES -- caja negra")
    print("=" * 78)
    casos = cargar_ejemplos()
    print(f"[*] Cargados {len(casos)} ejemplos de pruebas/ejemplos.jsonl")

    cliente = Cliente()
    registro = RegistroPatrones()
    try:
        if HACER_REPLAY:
            resultados = fase_replay(casos, cliente, registro)
        else:
            print("\n[*] REPLAY=0 -> se omite el reenvío; se usa lo grabado.")
            resultados = []
        estructura = fase_estructura(casos, resultados, registro)
        fase_sondeo(estructura, cliente, registro)
        escribir_resumen_md(casos, resultados)
    finally:
        registro.cerrar()

    print("\n[FIN] Hallazgos acumulados en:")
    print(f"  - {os.path.relpath(PATRONES_JSONL, RAIZ)}")
    print(f"  - {os.path.relpath(PATRONES_MD, RAIZ)}")
    print(f"  - {os.path.relpath(EJEMPLOS_NUEVOS, RAIZ)}")


if __name__ == "__main__":
    main()
