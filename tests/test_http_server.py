"""Stage 22 - HTTP server adapter tests (15).

Drives the stdlib-only ``KROFT_OSServer`` over real TCP:
  * exercise every API route (/api/search, /api/fuzzy, /api/suggest,
    /api/graph, /api/node, POST /api/crawl) and static serving,
  * assert CORS header, path-traversal guard, 404s, port binding,
    start/stop lifecycle, and the cli/ + repl/ integration (served
    through the DI container -- arch gate: cli/ never imports adapters).

The server is run on a FREE port (port=0) so tests never fight over 8080.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from services import VaultStreamCrawler, GraphQueryEngine, ContentIndex
from adapters.http_server import KROFT_OSServer


# --------------------------------------------------------------------------
# helpers
def _make_vault(tmp_path: Path) -> str:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text(
        "#python root concept [[B.md]] links to [[C.md]]", encoding="utf-8"
    )
    (vault / "B.md").write_text("#python leaf #idea about python", encoding="utf-8")
    (vault / "C.md").write_text("pythonic notes #todo", encoding="utf-8")
    return str(vault)


def _build_container(vault: str, with_index: bool = True) -> DependencyContainer:
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    if with_index:
        c.register_instance("ContentIndex", ContentIndex())
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"),
            c.resolve("IEventBus"),
            c.resolve("IGraphBuilder"),
            vault,
            index=c.resolve("ContentIndex") if with_index else None,
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(
            c.resolve("IGraphBuilder"),
            index=c.resolve("ContentIndex") if with_index else None,
        ),
    )
    return c


def _crawl(container: DependencyContainer) -> None:
    crawler = container.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())


def _start_server(container: DependencyContainer, port: int = 0) -> KROFT_OSServer:
    server = KROFT_OSServer(container, host="127.0.0.1", port=port)
    server.start()
    _wait_ready("127.0.0.1", server.port)
    return server


def _wait_ready(host: str, port: int, timeout: float = 5.0) -> None:
    """Block until the TCP port accepts a connection (server loop is up)."""
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:  # pragma: no cover - transient race
            last_exc = exc
            time.sleep(0.02)
    raise TimeoutError(f"server not ready on {host}:{port} -- {last_exc}")


def _get(host: str, port: int, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", path)
    return conn.getresponse()


def _post(host: str, port: int, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("POST", path, headers={"Content-Length": "0"})
    return conn.getresponse()


# --------------------------------------------------------------------------
# 1. /api/search
def test_api_search(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/search?q=python")
        assert r.status == 200
        body = json.loads(r.read().decode("utf-8"))
        norm = {_norm_id(b) for b in body}
        # A.md and B.md contain the token 'python'; C.md only has 'pythonic'
        # (a different token), so it is correctly excluded from an exact search.
        assert "A.MD" in norm and "B.MD" in norm
        assert "C.MD" not in norm
    finally:
        server.stop()


def _norm_id(s: str) -> str:
    return s.strip().upper()


# 2. /api/fuzzy  (pithon -> python)
def test_api_fuzzy(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/fuzzy?q=pithon")
        assert r.status == 200
        body = json.loads(r.read().decode("utf-8"))
        # 'pithon' fuzzy-matches 'python' (in A.md/B.md); membership is the
        # meaningful check (case-insensitive, robust to OS path casing).
        norm = {_norm_id(b) for b in body}
        assert "A.MD" in norm and "B.MD" in norm
    finally:
        server.stop()


# 3. /api/suggest
def test_api_suggest(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/suggest?prefix=py")
        assert r.status == 200
        body = json.loads(r.read().decode("utf-8"))
        assert any(t.startswith("py") for t in body)
        assert "python" in body
    finally:
        server.stop()


# 4. /api/graph
def test_api_graph(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/graph")
        assert r.status == 200
        g = json.loads(r.read().decode("utf-8"))
        assert "nodes" in g and "edges" in g
        assert len(g["nodes"]) == 3
        assert len(g["edges"]) >= 2
    finally:
        server.stop()


# 5. /api/node
def test_api_node(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/node?id=A.md")
        assert r.status == 200
        node = json.loads(r.read().decode("utf-8"))
        assert node.get("id", "").upper() == "A.MD"
        assert "label" in node
    finally:
        server.stop()


# 6. POST /api/crawl
def test_api_crawl_post(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _post("127.0.0.1", server.port, "/api/crawl")
        assert r.status == 200
        body = json.loads(r.read().decode("utf-8"))
        assert body == {"status": "triggered"}
    finally:
        server.stop()


# 7. static index.html
def test_static_index_html(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/")
        assert r.status == 200
        html = r.read().decode("utf-8")
        assert "<html" in html
        assert "KROFT_OS" in html
    finally:
        server.stop()


# 8. unknown path -> 404
def test_static_404(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/nonexistent")
        assert r.status == 404
    finally:
        server.stop()


# 9. CORS header present
def test_cors_header(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/graph")
        assert r.getheader("Access-Control-Allow-Origin") == "*"
    finally:
        server.stop()


# 10. start/stop lifecycle
def test_server_start_stop(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    server = KROFT_OSServer(c, host="127.0.0.1", port=0)
    assert server._server is None
    server.start()
    assert server._server is not None
    assert server.port > 0
    _wait_ready("127.0.0.1", server.port)
    server.stop()
    assert server._server is None


# 11. port conflict -> OSError (or fallback)
def test_server_port_binding(tmp_path):
    # Occupy a port with a raw listening socket (NO reuse), then attempt to
    # bind the server to the same port with reuse DISABLED so the actively
    # listening occupier reliably blocks the rebind on both Linux and Windows
    # (proving conflict handling surfaces an OSError rather than silently
    # stealing the port).
    from http.server import HTTPServer as _HS

    saved = _HS.allow_reuse_address
    _HS.allow_reuse_address = False
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        occupied_port = sock.getsockname()[1]
        c = _build_container(_make_vault(tmp_path))
        server = KROFT_OSServer(c, host="127.0.0.1", port=occupied_port)
        with pytest.raises(OSError):
            server.start()
        # The port must remain reported as the requested one (no silent remap).
        assert server.port == occupied_port
    finally:
        sock.close()
        _HS.allow_reuse_address = saved


# 12. cli cmd_serve does not crash (mocked server + immediate Ctrl-C)
def test_cli_serve(tmp_path, monkeypatch):
    from cli import commands

    vault = _make_vault(tmp_path)
    c = _build_container(vault)

    class FakeServer:
        def __init__(self):
            self._host = "127.0.0.1"
            self._port = 8080
            self._started = False
            self._stopped = False

        @property
        def port(self):
            return self._port

        def start(self):
            self._started = True

        def stop(self):
            self._stopped = True

    fake = FakeServer()
    c.register_instance("KROFT_OSServer", fake)

    # Make the serve loop exit immediately on the first sleep (simulated Ctrl-C).
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt))

    # Patch the container's vault args so _resolve_config does not touch disk config.
    args = type("A", (), {"host": "127.0.0.1", "port": 9999, "vault": vault})()
    # Build a container the same way main does, but with the fake server.
    commands.cmd_serve(args, c)
    assert fake._started is True
    assert fake._stopped is True


# 13. REPL `serve` verb does not crash
def test_repl_serve_verb(tmp_path):
    from kernel import Kernel
    from cli.repl import KROFT_OSRepl

    vault = _make_vault(tmp_path)
    c = _build_container(vault)

    class FakeServer:
        def __init__(self):
            self._host = "127.0.0.1"
            self._port = 8080
            self._started = False

        @property
        def port(self):
            return self._port

        def start(self):
            self._started = True

    fake = FakeServer()
    c.register_instance("KROFT_OSServer", fake)

    k = Kernel(c)
    k.initialize()
    k.start()
    it = iter(["serve 9999", "exit"])
    KROFT_OSRepl(k, c, reader=lambda: next(it)).run()
    assert fake._started is True
    assert k.state.name == "STOPPED"


# 14. empty index (index=None) -> suggest/search return []
def test_api_search_empty_index(tmp_path):
    # Build a container WITHOUT a ContentIndex: the engine/search resolve to
    # None-backed behaviour; /api/suggest must return [], /api/search too.
    c = _build_container(tmp_path / "v", with_index=False)
    _crawl(c)
    server = _start_server(c)
    try:
        r = _get("127.0.0.1", server.port, "/api/suggest?prefix=py")
        assert r.status == 200
        assert json.loads(r.read().decode("utf-8")) == []
        r2 = _get("127.0.0.1", server.port, "/api/search?q=python")
        assert r2.status == 200
        assert json.loads(r2.read().decode("utf-8")) == []
    finally:
        server.stop()


# 15. path traversal -> 403
def test_path_traversal_blocked(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    server = _start_server(c)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        # Send a raw, non-normalized path; BaseHTTPRequestHandler keeps it as-is.
        conn.request("GET", "/static/../../etc/passwd")
        r = conn.getresponse()
        assert r.status == 403
    finally:
        server.stop()
