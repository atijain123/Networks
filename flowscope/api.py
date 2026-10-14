from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .service import FlowScopeService


class FlowScopeHandler(SimpleHTTPRequestHandler):
    service: FlowScopeService

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json({"status": "ok", "service": "flowscope"})
        if self.path == "/api/state":
            return self._json(self.service.state())
        return super().do_GET()

    def do_POST(self):
        if self.path not in {"/api/optimize", "/api/simulate", "/api/reset"}:
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(content_length) or b"{}")
            if self.path == "/api/reset":
                return self._json(self.service.reset())
            seed = body.get("seed")
            seed = int(seed) if seed is not None else None
            if self.path == "/api/simulate":
                return self._json(self.service.simulate(seed=seed))
            return self._json(self.service.optimize(seed=seed or 20261013))
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, format: str, *args):
        return


def serve(service: FlowScopeService, directory: Path, port: int = 8000) -> ThreadingHTTPServer:
    handler: Callable = lambda *args, **kwargs: FlowScopeHandler(*args, directory=str(directory), **kwargs)
    FlowScopeHandler.service = service
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return server
