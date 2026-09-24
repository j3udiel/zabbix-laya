"""Interfaz local para experimentar con Laya y alertas de Zabbix."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

BASE = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(BASE / ".cache" / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
LOCK = threading.Lock()
router = None


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
        elif self.path == "/api/setup":
            self.reply(200, {"cases": json.loads((BASE / "alertas.json").read_text()),
                             "questions": json.loads((BASE / "preguntas.json").read_text())})
        elif self.path == "/api/health":
            self.reply(200, {"ready": router is not None, "model": "multilingual", "offline": True})
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
            state, questions = validate(json.loads(self.rfile.read(length)))
        except (ValueError, OSError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        if not LOCK.acquire(blocking=False):
            self.reply(429, {"error": "Laya está evaluando otra alerta. Vuelve a intentarlo en unos segundos."})
            return
        try:
            started = time.perf_counter()
            result = router.predict(state, questions, model="multilingual")
            self.reply(200, {"result": result, "seconds": time.perf_counter() - started,
                             "state": state, "questions": questions})
        except Exception as exc:
            print(f"Error de inferencia: {exc}", flush=True)
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
