"""Interfaz local para experimentar con Laya y alertas de Zabbix."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from importlib.metadata import version

BASE = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(BASE / ".cache" / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
LOCK = threading.Lock()
router = None


def model_metadata():
    ref = BASE / '.cache/huggingface/hub/models--convaiinnovations--laya/refs/main'
    return {'laya_version': version('laya'), 'model_revision': ref.read_text().strip() if ref.exists() else None}


def check_context(agent, state, questions):
    """Reject truncation for machine callers; tied to the pinned Laya 0.3.20 formatter."""
    from laya.common import serialize_state, render_options
    tok = agent.tok
    encode = lambda text: tok(text.replace(tok.mask_token, ' '), add_special_tokens=False)['input_ids']
    state_length = len(encode(serialize_state(state)))
    max_length = agent.cfg.get('max_len', 512)
    head_limit = agent.cfg.get('head_max_len', 192)
    for qdef in questions.values():
        q = agent._to_internal(qdef)
        options = [len(encode(' ' + option)) for option in render_options(q)]
        head_length = len(encode('%s question: %s' % (q['t'], q['ins'])))
        if any(n > 48 for n in options) or head_length + sum(n+1 for n in options) > head_limit:
            raise ValueError('Las instrucciones u opciones exceden el contexto de la pregunta.')
        if state_length + head_length + sum(n+1 for n in options) + 4 > max_length:
            raise ValueError('La alerta excede el contexto del modelo. Reduce las features; no se ha truncado.')


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("La solicitud debe ser un objeto JSON.")
    state = payload.get("state")
    if not isinstance(state, (dict, str)) or not state:
        raise ValueError("Introduce una alerta con contenido.")
    questions = payload.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 6:
        raise ValueError("Define entre una y seis preguntas.")
    for question in questions.values():
        if not isinstance(question, dict) or question.get("type") not in ("choice", "score", "noul"):
            raise ValueError("Cada pregunta debe ser choice, score o noul.")
        if not isinstance(question.get("instructions"), str) or not question["instructions"].strip():
            raise ValueError("Cada pregunta necesita instrucciones.")
        kind, criteria = question["type"], question.get("criteria")
        if kind == "choice" and (not isinstance(criteria, dict) or not 2 <= len(criteria) <= 10
                                 or not all(isinstance(v, str) for v in criteria.values())):
            raise ValueError("choice necesita entre 2 y 10 opciones con descripciones de texto.")
        if kind == "score" and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 6
                                or not all(isinstance(v, str) for v in criteria)):
            raise ValueError("score necesita entre 2 y 6 niveles de texto.")
    return state, questions


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.reply(200, (BASE / "ui.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/propuesta", "/propuesta.html"):
            self.reply(200, (BASE / "propuesta.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/setup":
            self.reply(200, {"cases": json.loads((BASE / "alertas.json").read_text()),
                             "questions": json.loads((BASE / "preguntas.json").read_text())})
        elif self.path == "/api/health":
            self.reply(200, {"ready": router is not None, "model": "multilingual", "offline": True, **model_metadata()})
        else:
            self.reply(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        if self.path != "/api/predict":
            self.reply(404, {"error": "Ruta no encontrada"})
            return
        # Browsers cannot submit cross-origin forms or JSON requests to this endpoint.
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self.reply(403, {"error": "Origen no permitido"})
            return
        if self.headers.get_content_type() != "application/json":
            self.reply(415, {"error": "Se requiere application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16000:
                raise ValueError("La solicitud debe ocupar entre 1 y 16000 bytes.")
            self.connection.settimeout(15)
            payload = json.loads(self.rfile.read(length))
            state, questions = validate(payload)
            strict_context = payload.get('strict_context', False)
            if not isinstance(strict_context, bool):
                raise ValueError('strict_context debe ser booleano.')
        except (ValueError, OSError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        if not LOCK.acquire(blocking=False):
            self.reply(429, {"error": "Laya está evaluando otra alerta. Vuelve a intentarlo en unos segundos."})
            return
        try:
            if strict_context:
                check_context(router.load('multilingual'), state, questions)
            started = time.perf_counter()
            result = router.predict(state, questions, model="multilingual")
            self.reply(200, {"result": result, "seconds": time.perf_counter() - started,
                             "state": state, "questions": questions, **model_metadata()})
        except ValueError as exc:
            self.reply(422, {"error": str(exc) if strict_context else 'Pregunta no válida.'})
        except Exception as exc:
            print(f"Error de inferencia: {type(exc).__name__}", flush=True)
            self.reply(500, {"error": "No se pudo evaluar la alerta. Revisa el contenido y el registro del servidor."})
        finally:
            LOCK.release()


def main():
    global router
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import torch
    from laya import Router
    torch.set_num_threads(2)
    print("Cargando Laya multilingüe desde la caché local...", flush=True)
    router = Router(device="cpu", max_loaded=1)
    router.load("multilingual")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Laya listo: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
