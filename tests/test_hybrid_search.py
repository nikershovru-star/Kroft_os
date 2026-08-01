"""Stage 30 - Hybrid Search tests (8).

RRF fusion (k=60) of lexical (ContentIndex) + semantic (SemanticIndex),
plus HTTP endpoint and REPL dispatch. Zero regression: missing semantic
-> lexical-only; missing index -> semantic-only; missing both -> [].

NOTE (same as Stage 29): the default MockEmbeddingAdapter is deterministic
but NOT semantically meaningful, so we assert *fusion/ranking* behaviour
(stability, degradation, tie-break, top-k) on controlled mocks rather than
real-world relevance.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import socket
import time

import pytest

from services import GraphQueryEngine, SemanticIndex
from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter, MockEmbeddingAdapter
from adapters.http_server import KROFT_OSServer


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
    server = KROFT_OSServer(container, host="127.0.0.1", port=port)
    server.start()
    _wait_ready("127.0.0.1", server.port)
    return server


def _req(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    return conn.getresponse()


def _build_container(vault):
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_instance("ContentIndex", object())  # replaced by crawl below
    c.register_instance("SemanticIndex", SemanticIndex())
    c.register_instance("Embedding", MockEmbeddingAdapter())
    from services import ContentIndex, VaultStreamCrawler
    c.register_instance("ContentIndex", ContentIndex())
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
    return c


def _engine(semantic=True):
    g = InMemoryGraphBuilder()
    c = GraphQueryEngine(g)
    if semantic:
        c._semantic_index = SemanticIndex()
        c._embedding = MockEmbeddingAdapter()
    return c, g


# --------------------------------------------------------------------- tests
class TestRRF:
    def test_rrf_fusion_boosts_overlap(self):
        """A node in BOTH lexical + semantic ranks gets the highest RRF score."""
        e, g = _engine()
        # Mock embeddings: same text -> same vector, so semantic order is deterministic
        e._semantic_index.add("a", e._embedding.embed("x"))
        e._semantic_index.add("b", e._embedding.embed("y"))
        e._semantic_index.add("d", e._embedding.embed("z"))
        # Patch lexical search to return fixed order
        e.search = lambda q: ["b", "a", "c"]
        # Semantic returns [b, a, d]
        e._semantic_index.search = lambda emb, top_k: [("b", 0.9), ("a", 0.8), ("d", 0.7)]
        result = e.hybrid_search("x", top_k=3)
        ids = [nid for nid, _ in result]
        # b is rank-1 lexical + rank-1 semantic => highest RRF (beats a's 2/62)
        assert ids[0] == "b"
        # a is rank-2 lexical + rank-2 semantic => second (2/62 < 2/61)
        assert ids[1] == "a"

    def test_hybrid_only_lexical(self):
        """Without semantic wired, hybrid degrades to lexical-only RRF."""
        e, g = _engine(semantic=False)
        e.search = lambda q: ["z", "y"]
        result = e.hybrid_search("q", top_k=2)
        assert [nid for nid, _ in result] == ["z", "y"]

    def test_hybrid_only_semantic(self):
        """Without lexical index, hybrid degrades to semantic-only RRF."""
        e, g = _engine()
        e.search = lambda q: []
        e._semantic_index.add("m", e._embedding.embed("q"))
        e._semantic_index.search = lambda emb, top_k: [("m", 0.5)]
        result = e.hybrid_search("q", top_k=1)
        assert result == [("m", 1.0 / (60 + 1))]

    def test_hybrid_empty_query(self):
        e, g = _engine()
        assert e.hybrid_search("") == []
        assert e.hybrid_search("   ") == []

    def test_hybrid_top_k(self):
        e, g = _engine(semantic=False)
        e.search = lambda q: [str(i) for i in range(100)]
        result = e.hybrid_search("q", top_k=5)
        assert len(result) == 5

    def test_hybrid_deterministic_tiebreak(self):
        """Same RRF score -> sorted by node id ascending (real tie)."""
        e, g = _engine(semantic=False)
        # b only in lexical (rank 1), a only in semantic (rank 1) => both 1/61
        e.search = lambda q: ["b"]
        e._semantic_index = SemanticIndex()
        e._embedding = MockEmbeddingAdapter()
        e._semantic_index.add("a", e._embedding.embed("q"))
        e._semantic_index.search = lambda emb, top_k: [("a", 0.5)]
        result = e.hybrid_search("q", top_k=2)
        # Both have same RRF score (1/61), tie-break by nid asc -> a, b
        assert [nid for nid, _ in result] == ["a", "b"]

    def test_hybrid_api_200(self, tmp_path):
        """HTTP /api/hybrid returns 200 and JSON list of [id, score]."""
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "py.md").write_text("python venv configure", encoding="utf-8")
        (vault / "cook.md").write_text("tomato soup recipe", encoding="utf-8")
        c = _build_container(str(vault))
        asyncio.run(c.resolve("VaultStreamCrawler").crawl())
        server = _start_server(c)
        try:
            r = _req(server.port, "/api/hybrid?q=python%20configure&top_k=2")
            assert r.status == 200
            body = json.loads(r.read().decode("utf-8"))
            assert isinstance(body, list)
            assert len(body) == 2
            assert body[0][0] == "py.md"
            # regression: /api/semantic still 200
            r2 = _req(server.port, "/api/semantic?q=python&top_k=1")
            assert r2.status == 200
        finally:
            server.stop()

    def test_hybrid_repl_dispatch(self):
        """REPL 'hybrid python' calls engine.hybrid_search and prints JSON."""
        from cli.repl import KROFT_OSRepl
        from services import ContentIndex
        c = DependencyContainer()
        c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
        c.register_instance("IEventBus", InMemoryEventBus())
        c.register_instance("ICapabilityRegistry", CapabilityRegistry())
        c.register_instance("ContentIndex", ContentIndex())
        c.register_instance("SemanticIndex", SemanticIndex())
        c.register_instance("Embedding", MockEmbeddingAdapter())
        c.register_factory(
            "GraphQueryEngine",
            lambda: GraphQueryEngine(
                c.resolve("IGraphBuilder"),
                index=c.resolve("ContentIndex"),
                semantic_index=c.resolve("SemanticIndex"),
                embedding=c.resolve("Embedding"),
            ),
        )
        repl = KROFT_OSRepl.__new__(KROFT_OSRepl)
        repl._container = c
        # capture printed output
        import io
        import sys
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            repl._do_hybrid(["python", "--top-k", "3"])
        finally:
            sys.stdout = old
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert isinstance(parsed, list)
