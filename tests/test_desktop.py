"""Stage 31 - Desktop Automation tests (8).

Covers the IDesktop port, Mock/PyAutoGUI adapters, DesktopService
orchestration, HTTP endpoints, and CLI/REPL dispatch.

Default wiring is MockDesktopAdapter (no real mouse/keyboard), so all
tests run headless and deterministic. PyAutoGUIAdapter is only exercised
for its lazy-fail contract (pyautogui is not installed in CI).
"""
from __future__ import annotations

import asyncio
import base64
import http.client
import json
import socket
import time

import pytest

from contracts import IDesktop
from adapters import MockDesktopAdapter, PyAutoGUIAdapter
from services import DesktopService
from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.http_server import KnowledgeOSServer


# ------------------------------------------------------------------- helpers
def _wait_ready(host, port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.02)
    raise TimeoutError(f"server on {host}:{port} never came up")


def _start_server(container, port=0):
    server = KnowledgeOSServer(container, host="127.0.0.1", port=port)
    server.start()
    _wait_ready("127.0.0.1", server.port)
    return server


def _req(method, port, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data,
                     headers={"Content-Type": "application/json"})
    else:
        conn.request(method, path)
    return conn.getresponse()


def _build_container(vault):
    """Full container including the DesktopService (Stage 31)."""
    from services import ContentIndex, SemanticIndex, VaultStreamCrawler
    from adapters import MockEmbeddingAdapter
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_instance("ContentIndex", ContentIndex())
    c.register_instance("SemanticIndex", SemanticIndex())
    c.register_instance("Embedding", MockEmbeddingAdapter())
    c.register_instance("IDesktop", MockDesktopAdapter())
    c.register_factory(
        "DesktopService",
        lambda: DesktopService(c.resolve("IDesktop")),
    )
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"),
            c.resolve("IEventBus"),
            c.resolve("IGraphBuilder"),
            vault,
            index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: __import__("services").GraphQueryEngine(
            c.resolve("IGraphBuilder"),
            index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    return c


# --------------------------------------------------------------------- tests
class TestMockDesktopAdapter:
    def test_click_noop(self):
        MockDesktopAdapter().click(10, 20)  # no exception

    def test_screenshot_returns_png(self):
        png = MockDesktopAdapter().screenshot()
        assert png.startswith(b"\x89PNG")

    def test_cursor_zero(self):
        assert MockDesktopAdapter().cursor_position() == (0, 0)

    def test_open_noop(self):
        MockDesktopAdapter().open_app("notepad")  # no exception


class TestDesktopService:
    def test_service_delegates_click(self):
        DesktopService(MockDesktopAdapter()).click_at(5, 5)  # no exception

    def test_service_unwired_raises(self):
        with pytest.raises(RuntimeError):
            DesktopService(None).click_at(1, 1)


class TestPyAutoGUIAdapter:
    def test_lazy_import_state(self):
        a = PyAutoGUIAdapter()
        assert a._pg is None  # not imported until first use


class TestHTTPDesktop:
    def test_api_desktop_cursor_200(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "a.md").write_text("hello world", encoding="utf-8")
        c = _build_container(str(vault))
        asyncio.run(c.resolve("VaultStreamCrawler").crawl())
        server = _start_server(c)
        try:
            r = _req("GET", server.port, "/api/desktop/cursor")
            assert r.status == 200
            j = json.loads(r.read().decode("utf-8"))
            assert j == {"x": 0, "y": 0}
            # POST endpoints also 200 against the Mock adapter
            r2 = _req("POST", server.port, "/api/desktop/click", {"x": 1, "y": 2})
            assert r2.status == 200
            assert json.loads(r2.read().decode("utf-8")) == {"ok": True}
            # screenshot returns raw PNG bytes (Mock 1x1 placeholder)
            r3 = _req("GET", server.port, "/api/desktop/screenshot")
            assert r3.status == 200
            assert r3.getheader("Content-Type") == "image/png"
            assert r3.read().startswith(b"\x89PNG")
        finally:
            server.stop()
