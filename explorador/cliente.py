"""Cliente instrumentado para la caja negra.

- Lee token y URL de variables de entorno o del .env del proyecto.
- Respeta 10 req/s; cuenta requests del dia (persistido en .rate_state.json).
- Descarta (y reintenta) respuestas de infraestructura (X-Frontier-Infra).
- Registra TODA request al servicio en experimentos.jsonl con su hipotesis.
- Guarda el cuerpo crudo: JSON si lo es, texto exacto si no.
"""
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LOG = RAIZ / "experimentos.jsonl"
ESTADO = RAIZ / ".rate_state.json"
MIN_INTERVALO = 0.12  # ~8 req/s, margen bajo el limite de 10
LIMITE_DIA = 8000


def _cargar_env():
    env = dict(os.environ)
    f = RAIZ / ".env"
    if f.exists():
        for linea in f.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.startswith("#"):
                k, v = linea.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


class Cliente:
    def __init__(self, token=None, base=None):
        env = _cargar_env()
        self.token = token or env["FRONTIER_TOKEN"]
        self.base = (base or env["BASE_URL"]).rstrip("/")
        self._ultimo = 0.0
        self._siguiente_id = self._max_id() + 1

    # ---- utilidades de log / cuota
    @staticmethod
    def _max_id():
        if not LOG.exists():
            return 0
        n = 0
        for linea in LOG.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                n = max(n, json.loads(linea).get("id", 0))
        return n

    def _contar_dia(self):
        hoy = time.strftime("%Y-%m-%d")
        est = {}
        if ESTADO.exists():
            est = json.loads(ESTADO.read_text())
        if est.get("dia") != hoy:
            est = {"dia": hoy, "n": 0}
        est["n"] += 1
        ESTADO.write_text(json.dumps(est))
        if est["n"] > LIMITE_DIA - 200:
            raise RuntimeError(f"Cerca del limite diario: {est['n']}")

    # ---- HTTP crudo
    def crudo(self, metodo, ruta, cuerpo=None, headers=None, con_token=True):
        """Devuelve (status, texto, headers_dict). Reintenta si es rate-limit de infra."""
        for _ in range(6):
            espera = MIN_INTERVALO - (time.time() - self._ultimo)
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.time()
            self._contar_dia()
            h = dict(headers or {})
            if con_token:
                h.setdefault("Authorization", f"Bearer {self.token}")
            if isinstance(cuerpo, (dict, list)):
                data = json.dumps(cuerpo, ensure_ascii=False).encode()
                h.setdefault("Content-Type", "application/json")
            elif isinstance(cuerpo, str):
                data = cuerpo.encode()
            else:
                data = cuerpo
            req = urllib.request.Request(self.base + ruta, data=data, headers=h, method=metodo)
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    status, raw, hdr = r.status, r.read(), dict(r.headers)
            except urllib.error.HTTPError as e:
                status, raw, hdr = e.code, e.read(), dict(e.headers)
            except (TimeoutError, OSError) as e:
                # timeout / red: es un dato, no una respuesta del servicio
                self.ultimo_error_red = f"{type(e).__name__}: {e}"
                return 0, f"<<SIN_RESPUESTA {time.time() - t0:.1f}s {type(e).__name__}>>", {}
            hl = {k.lower(): v for k, v in hdr.items()}
            if hl.get("x-frontier-infra") == "rate-limit":
                time.sleep(1.0)
                continue
            return status, raw.decode("utf-8", errors="replace"), hl
        raise RuntimeError("rate-limit persistente")

    @staticmethod
    def _parse(texto):
        try:
            return json.loads(texto)
        except ValueError:
            return texto

    def _log(self, seq, hipotesis, request, status, respuesta, x_req, conclusion=None):
        fila = {
            "id": self._siguiente_id, "seq": seq, "x_req": x_req,
            "hipotesis": hipotesis, "request": request,
            "status": status, "response": respuesta,
        }
        if conclusion:
            fila["conclusion"] = conclusion
        self._siguiente_id += 1
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        return fila

    # ---- API de alto nivel
    def reset(self):
        return self.crudo("POST", "/__reset")

    def msg(self, m, seq, hipotesis, conclusion=None):
        """POST /msg {"m": m}; registra en el log; devuelve la fila."""
        cuerpo = {"m": m}
        status, texto, hl = self.crudo("POST", "/msg", cuerpo)
        return self._log(seq, hipotesis, cuerpo, status, self._parse(texto),
                         hl.get("x-req"), conclusion)

    def raw_logged(self, metodo, ruta, cuerpo, seq, hipotesis, headers=None, con_token=True):
        status, texto, hl = self.crudo(metodo, ruta, cuerpo, headers, con_token)
        req = {"metodo": metodo, "ruta": ruta, "cuerpo": cuerpo}
        return self._log(seq, hipotesis, req, status, self._parse(texto), hl.get("x-req"))
