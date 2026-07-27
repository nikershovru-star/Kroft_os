"""Stage 32 - Desktop Orchestrator tests (6).

Covers DesktopOrchestrator bridging GraphQueryEngine (hybrid_search) and
DesktopService (launch), plus HTTP endpoints. Default wiring is Mock, so
open_note/list_notes run headless and deterministic.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time

import pytest

from services import (
    DesktopOrchestrator,
    DesktopService,
    GraphQueryEngine,
    SemanticIndex,
)
from adapters import MockDesktopAdapter, MockEmbeddingAdapter
from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.http_server import KnowledgeOSServer


class FakeFS:
    """Minimal IFileSystem stub that "has" a fixed set of files."""
    def __init__(self, existing):
        self._existing = set(existing)
    def exists(self, path: str) -> bool:
        return os.path.basename(path) in self._existing


def _orch(vault="/tmp/vault"):
    g = InMemoryGraphBuilder()
    engine = GraphQueryEngine(g)
    desktop = DesktopService(MockDesktopAdapter())
    fs = FakeFS({"note.md", "py.md", "cook.md"})
    return DesktopOrchestrator(engine, desktop, fs, vault), engine, desktop


# ----------------------------------------------------------------- tests
class TestOpenNote:
    def test_open_note_empty_query(self):
        o, _, _ = _orch()
        assert o.open_note("") == {"error": "empty query"}
        assert o.open_note("   ") == {"error": "empty query"}

    def test_open_note_not_found(self):
        o, e, _ = _orch()
        e.search = lambda q: []  # lexical empty
        # also neutralize semantic
        e._semantic_index = SemanticIndex()
        e._embedding = MockEmbeddingAdapter()
        e._semantic_index.search = lambda emb, top_k: []
        assert o.open_note("xyz") == {"error": "no results", "query": "xyz"}

    def test_open_note_success(self):
        o, e, d = _orch()
        e.hybrid_search = lambda q, top_k: [("note.md", 0.95)]
        result = o.open_note("test")
        assert result["ok"] is True
        assert result["opened"] == "note.md"
        assert result["score"] == 0.95


class TestListNotes:
    def test_list_notes_returns_ranked(self):
        o, e, _ = _orch()
        e.hybrid_search = lambda q, top_k: [("a.md", 0.9), ("b.md", 0.8)]
        result = o.list_notes("q", top_k=2)
        assert len(result) == 2
        assert result[0]["id"] == "a.md"
        assert result[0]["score"] == 0.9


# ------------------------------------------------------------------ HTTP
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
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data,
                     headers={"Content-Type": "application/json"})
    else:
        conn.request(method, path)
    return conn.getresponse()


def _build_container(vault):
    from services import ContentIndex, VaultStreamCrawler
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
        lambda: GraphQueryEngine(
            c.resolve("IGraphBuilder"),
            index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    c.register_factory(
        "DesktopOrchestrator",
        lambda: DesktopOrchestrator(
            c.resolve("GraphQueryEngine"),
            c.resolve("DesktopService"),
            c.resolve("IFileSystem"),
            vault,
        ),
    )
    return c


class TestHTTP:
    def test_api_open_note_200(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "py.md").write_text("python venv configure", encoding="utf-8")
        (vault / "cook.md").write_text("tomato soup recipe", encoding="utf-8")
        c = _build_container(str(vault))
        asyncio.run(c.resolve("VaultStreamCrawler").crawl())
        server = _start_server(c)
        try:
            r = _req("POST", server.port, "/api/desktop/open_note",
                     {"query": "python configure", "top_k": 1})
            assert r.status == 200
            j = json.loads(r.read().decode("utf-8"))
            assert j.get("ok") is True
            assert j["opened"] == "py.md"
        finally:
            server.stop()

    def test_api_list_notes_200(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "py.md").write_text("python venv configure", encoding="utf-8")
        (vault / "cook.md").write_text("tomato soup recipe", encoding="utf-8")
        c = _build_container(str(vault))
        asyncio.run(c.resolve("VaultStreamCrawler").crawl())
        server = _start_server(c)
        try:
            r = _req("POST", server.port, "/api/desktop/list_notes",
                     {"query": "python", "top_k": 2})
            assert r.status == 200
            j = json.loads(r.read().decode("utf-8"))
            assert isinstance(j, list)
            assert len(j) <= 2
            assert j[0]["id"] == "py.md"
        finally:
            server.stop()
