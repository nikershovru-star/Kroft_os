"""HTTP server adapter (Stage 22). Stdlib ONLY -- no third-party web frameworks.

Threading HTTPServer + BaseHTTPRequestHandler. Serves JSON API + static files.

Architecture contract:
  * `http.server` / `threading` are stdlib -- this adapter stays axis-clean
    (adapters may import only contracts + stdlib; here we need no contracts).
  * The server resolves its collaborators (`GraphQueryEngine`, `ContentIndex`)
    from the DI container passed into it by the composition root (main.py),
    never importing them directly. cli/ also resolves `KnowledgeOSServer` by
    name -- so cli/ never imports this adapter (arch gate: cli -> no adapters).
"""
from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse


# Allow immediate port re-bind after stop() (Windows: TIME_WAIT sockets).
HTTPServer.allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    """Per-request handler. The container is injected once at server start."""

    def __init__(self, container: Any, *args, **kwargs):
        # BaseHTTPRequestHandler calls __init__(self, request, client_address,
        # server); *args/**kwargs proxy that through to super().__init__.
        self._container = container
        super().__init__(*args, **kwargs)

    # ----- routing -----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # Resolve lazily per-request (singletons; cheap on a warm container).
        # ContentIndex may be unregistered (e.g. index=None test) -> None,
        # which makes /api/suggest return [].
        engine = self._container.resolve("GraphQueryEngine")
        index = self._container.resolve("ContentIndex") if self._container.has("ContentIndex") else None

        if path == "/api/search":
            q = qs.get("q", [""])[0]
            self._json_response(engine.search(q))
        elif path == "/api/fuzzy":
            q = qs.get("q", [""])[0]
            self._json_response(engine.fuzzy_search(q))
        elif path == "/api/suggest":
            prefix = qs.get("prefix", [""])[0]
            self._json_response(index.suggest(prefix) if index else [])
        elif path == "/api/graph":
            self._json_response(engine._snapshot())
        elif path == "/api/node":
            nid = qs.get("id", [""])[0]
            g = engine._snapshot()
            node = next((n for n in g["nodes"] if n["id"] == nid), None)
            self._json_response(node or {})
        elif path == "/api/stats/centrality":
            self._json_response(engine.centrality())
        elif path == "/api/stats/components":
            self._json_response(engine.connected_components())
        elif path == "/api/stats/pagerank":
            self._json_response(engine.pagerank())
        elif path == "/":
            self._serve_static("index.html")
        elif path.startswith("/static/"):
            self._serve_static(path[8:])
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/crawl":
            # Stage 27 integration hook: trigger crawl via WatchService. The
            # actual crawl pipeline is wired elsewhere; here we simply signal.
            self._json_response({"status": "triggered"})
        else:
            self.send_error(404)

    # ----- response helpers -----
    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel_path):
        base = os.path.join(os.path.dirname(__file__), "static")
        base_norm = os.path.normpath(base)
        target = os.path.normpath(os.path.join(base, rel_path))
        # Path-traversal guard: target must stay inside the static dir.
        if target != base_norm and not target.startswith(base_norm + os.sep):
            self.send_error(403)
            return
        if not os.path.exists(target) or not os.path.isfile(target):
            self.send_error(404)
            return
        self.send_response(200)
        mime, _ = mimetypes.guess_type(target)
        self.send_header("Content-Type", mime or "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(target, "rb") as f:
            self.wfile.write(f.read())

    def log_message(self, format, *args):
        pass  # suppress default stderr logging


class KnowledgeOSServer:
    """HTTP server wrapper. Runs serve_forever in a daemon thread."""

    def __init__(self, container: Any, host: str = "127.0.0.1", port: int = 8080):
        self._container = container
        self._host = host
        self._port = port
        self._server = None
        self._thread = None

    def start(self):
        if self._server is not None:
            raise RuntimeError("server already started")
        # port=0 -> OS assigns a free port (used by tests to avoid clashes).
        self._server = HTTPServer((self._host, self._port), self._make_handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def _make_handler(self, *args, **kwargs):
        return _Handler(self._container, *args, **kwargs)

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            # server_close() frees the socket so the port is reusable
            # immediately (critical on Windows; otherwise TIME_WAIT binds it).
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def port(self) -> int:
        """Actual bound port (meaningful when started with port=0)."""
        if self._server is None:
            return self._port
        return self._server.server_address[1]
