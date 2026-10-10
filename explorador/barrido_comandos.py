"""Barrido de control por comando, con tope duro de requests.

Por comando: un texto base (barrido completo, orden 0..96) y variantes de un
solo caracter. Para cada variante se prueba primero el control PREDICHO por el
modelo de pesos (-3 * 10^idx_desde_el_final * delta_ord, mod 97); si falla se
hace barrido completo. Usa ids/montos inexistentes para no mutar estado
(ALTA si crea cuentas: se hace reset al final).

Una respuesta que no sea E201/E202 se toma como 'control aceptado', y se
verifica con cc+1: si cc+1 NO da E202, otro error se evalua ANTES que el control.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cliente import Cliente  # noqa: E402

TOPE_TOTAL = 700
M = 97


class Presupuesto:
    def __init__(self, tope):
        self.tope, self.usado = tope, 0

    def gastar(self):
        self.usado += 1
        if self.usado > self.tope:
            raise RuntimeError(f"tope de {self.tope} requests alcanzado")


def err_de(fila):
    r = fila["response"]
    return r.get("error") if isinstance(r, dict) else None


def idx_desde_final(texto, pos):
    """Indice (desde el final) de texto[pos] contando solo alfanumericos."""
    alnum = [i for i, ch in enumerate(texto) if ch.isalnum()]
    return len(alnum) - 1 - alnum.index(pos)


def predecir(base_cc, base, var):
    """Delta predicho por el modelo de CONSULTA para un cambio de un caracter."""
    pos = next(i for i, (a, b) in enumerate(zip(base, var)) if a != b)
    d = ord(var[pos]) - ord(base[pos])
    return (base_cc - 3 * pow(10, idx_desde_final(base, pos), M) * d) % M


def barrer(c, pres, texto, seq, hip, adivina=None):
    orden = list(range(M))
    if adivina is not None:
        orden.remove(adivina)
        orden.insert(0, adivina)
    for n in orden:
        pres.gastar()
        f = c.msg(f"{texto};{n}", seq, f"{hip} (cc={n})")
        if f["status"] == 0:
            # timeout: reintentar una vez; si se repite, candidato a control valido lento
            pres.gastar()
            f = c.msg(f"{texto};{n}", seq, f"{hip} (cc={n}) REINTENTO tras timeout")
            if f["status"] == 0:
                print(f"   !! timeout repetido en cc={n} para {texto!r}", flush=True)
                return n, f, "timeout"
        if err_de(f) not in ("E201", "E202"):
            pres.gastar()
            g = c.msg(f"{texto};{(n + 1) % M}", seq, f"{hip}: contraprueba cc+1")
            evaluado = err_de(g) == "E202"
            return n, f, evaluado
    return None, None, None


# base y variantes (un caracter cambiado cada una)
PLAN = {
    "DEPOSITO": ("DEPOSITO;AC-9001;1000",
                 ["DEPOSITO;AC-9001;1001", "DEPOSITO;AC-9001;1010", "DEPOSITO;AC-9001;2000",
                  "DEPOSITO;AC-9002;1000", "DEPOSITO;AC-9001;10000"]),
    "TRANSFER": ("TRANSFER;AC-9001;AC-9002;1000",
                 ["TRANSFER;AC-9001;AC-9002;1001", "TRANSFER;AC-9001;AC-9002;1010",
                  "TRANSFER;AC-9001;AC-9003;1000", "TRANSFER;AC-9001;AC-9002;10000"]),
    "ALTA": ("ALTA;Ana",
             ["ALTA;Anb", "ALTA;Aoa", "ALTA;Bna", "ALTA;Anaa"]),
    "ANULA": ("ANULA;OP-9001",
              ["ANULA;OP-9002", "ANULA;OP-9011", "ANULA;OP-90010"]),
}


def main():
    c = Cliente()
    c.reset()
    pres = Presupuesto(TOPE_TOTAL)
    resultados = {}
    try:
        for cmd, (base, variantes) in PLAN.items():
            cc0, f0, ev0 = barrer(c, pres, base, f"pesos_{cmd}", f"{cmd}: base {base!r}")
            print(f"[{cmd}] base {base!r}: cc={cc0} control_evaluado={ev0} resp={f0 and f0['response']}", flush=True)
            resultados[base] = (cc0, ev0)
            if cc0 is None:
                continue
            for v in variantes:
                try:
                    pred = predecir(cc0, base, v)
                except StopIteration:
                    pred = None  # variante cambia longitud: sin prediccion simple
                cc, f, ev = barrer(c, pres, v, f"pesos_{cmd}", f"{cmd}: variante {v!r}", pred)
                acierto = (cc == pred) if pred is not None else None
                print(f"   {v!r:42} cc={cc} predicho={pred} acierto={acierto} eval={ev} (usado {pres.usado})", flush=True)
                resultados[v] = (cc, ev)
    except RuntimeError as e:
        print("PARADO:", e)
    c.reset()
    pathlib.Path(__file__).with_name("pesos_cmds.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1))
    print("requests usadas:", pres.usado)


if __name__ == "__main__":
    main()
