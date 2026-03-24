import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable


class HealthHandler(BaseHTTPRequestHandler):
    metrics_fn: Callable[[], dict] = lambda: {}

    def do_GET(self):
        if self.path == "/health":
            data = self.metrics_fn()
            body = json.dumps({"status": "ok", **data}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


class HealthServer:
    def __init__(self, port: int, metrics_fn: Callable[[], dict]):
        self._port = port
        self._metrics_fn = metrics_fn
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._port == 0:
            return

        handler = type("H", (HealthHandler,), {"metrics_fn": staticmethod(self._metrics_fn)})
        self._server = HTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
