"""Stage 29 - Semantic Search tests (10).

Covers MockEmbeddingAdapter determinism/norm, SemanticIndex search/top_k/
empty/remove/snapshot, GraphQueryEngine proxy, HTTP endpoint, crawler
population, and snapshot round-trip.

NOTE: the default MockEmbeddingAdapter is deterministic but NOT semantically
meaningful (it does not map similar text to nearby vectors). These tests
therefore assert *infrastructure* behaviour (determinism, ranking stability,
top-k truncation, persistence) — not that "python" outranks "cooking" on
real semantics. That property belongs to the OpenAI/sentence-transformers
adapter (out of the arch gate).
"""
from __future__ import annotations

import asyncio
import http.client
import json
import math
import socket
import time

import pytest

from contracts import ISnapshotable
from adapters import MockEmbeddingAdapter
from services import SemanticIndex, GraphQueryEngine, VaultStreamCrawler, ContentIndex
from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.http_server import KROFT_OSServer


# ---------------------------------------------------------------------- helpers
def _wait_ready(host, port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.05)
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
    c.register_instance("ContentIndex", ContentIndex())
    c.register_instance("SemanticIndex", SemanticIndex())
    c.register_instance("Embedding", MockEmbeddingAdapter())
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


def _make_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text("python venv pip install", encoding="utf-8")
    (vault / "B.md").write_text("cooking recipe tomato soup", encoding="utf-8")
    (vault / "C.md").write_text("python asyncio coroutine", encoding="utf-8")
    return str(vault)


# ---------------------------------------------------------------------- tests
def test_mock_embedding_deterministic():
    emb = MockEmbeddingAdapter()
    v1 = emb.embed("hello world")
    v2 = emb.embed("hello world")
    assert v1 == v2
    assert len(v1) == 128


def test_mock_embedding_normalized():
    emb = MockEmbeddingAdapter()
    v = emb.embed("any text here")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_semantic_index_add_search():
    si = SemanticIndex()
    emb = MockEmbeddingAdapter()
    si.add("A", emb.embed("alpha beta"))
    si.add("B", emb.embed("gamma delta"))
    res = si.search(emb.embed("alpha beta"), top_k=2)
    assert res[0][0] == "A"


def test_semantic_index_top_k():
    si = SemanticIndex()
    emb = MockEmbeddingAdapter()
    for i in range(5):
        si.add(f"doc{i}", emb.embed(f"doc {i} content"))
    res = si.search(emb.embed("doc 0 content"), top_k=2)
    assert len(res) == 2


def test_semantic_index_empty():
    si = SemanticIndex()
    assert si.search([1.0, 0.0] * 64) == []


def test_semantic_index_remove():
    si = SemanticIndex()
    emb = MockEmbeddingAdapter()
    si.add("A", emb.embed("alpha"))
    si.remove("A")
    assert si.search(emb.embed("alpha")) == []


def test_graph_engine_semantic():
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "A", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    engine = GraphQueryEngine(g, semantic_index=si, embedding=emb)
    res = engine.semantic_search("alpha")
    # Current contract: list of (node_id, score) tuples (generic graph refactor).
    assert isinstance(res, list)
    assert res and res[0][0] == "A.md"


def test_api_semantic_endpoint(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    asyncio.run(c.resolve("VaultStreamCrawler").crawl())
    server = _start_server(c)
    try:
        r = _req(server.port, "/api/semantic?q=python&top_k=2")
        assert r.status == 200
        data = json.loads(r.read().decode("utf-8"))
        # Current contract: list of [node_id, score] pairs (generic graph refactor).
        assert isinstance(data, list)
        assert len(data) <= 2
        assert all(isinstance(row, list) and len(row) == 2 for row in data)
    finally:
        server.stop()


def test_crawl_populates_semantic(tmp_path):
    c = _build_container(_make_vault(tmp_path))
    asyncio.run(c.resolve("VaultStreamCrawler").crawl())
    si = c.resolve("SemanticIndex")
    assert len(si) == 3  # A.md, B.md, C.md


def test_snapshot_roundtrip():
    si = SemanticIndex()
    emb = MockEmbeddingAdapter()
    si.add("A", emb.embed("alpha"))
    si.add("B", emb.embed("beta"))
    # ISnapshotable contract satisfied.
    assert isinstance(si, ISnapshotable)
    snap = si.snapshot()
    si2 = SemanticIndex()
    si2.restore(snap)
    res1 = si.search(emb.embed("alpha"), top_k=2)
    res2 = si2.search(emb.embed("alpha"), top_k=2)
    assert res1 == res2


# ----------------------------------------------------------------------
# P0-A: abstention threshold tests
# ----------------------------------------------------------------------

def test_semantic_search_respects_abstain_threshold():
    """When best score < threshold, semantic_search returns [] (abstain)."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "alpha beta", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    engine = GraphQueryEngine(g, semantic_index=si, embedding=emb)

    # Query "zeta" won't match "alpha beta" well — Jaccard score will be 0.
    results = engine.semantic_search("zeta", top_k=5, abstain_threshold=0.01)
    assert results == []


def test_semantic_search_returns_results_when_above_threshold():
    """When best score >= threshold, semantic_search returns filtered results."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "alpha beta", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    engine = GraphQueryEngine(g, semantic_index=si, embedding=emb)

    # "alpha beta" should match "alpha beta" with highest Jaccard score (1.0).
    results = engine.semantic_search("alpha beta", top_k=5, abstain_threshold=0.5)
    assert len(results) > 0
    assert all(score >= 0.5 for _, score in results)


def test_semantic_search_zero_regression_no_threshold():
    """Without abstain_threshold, semantic_search behaves as before."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "alpha beta", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    engine = GraphQueryEngine(g, semantic_index=si, embedding=emb)

    # No threshold — should return results even if low confidence.
    results = engine.semantic_search("zeta", top_k=5)
    # Results may or may not be empty, but the method should not raise.
    assert isinstance(results, list)


def test_hybrid_search_respects_abstain_threshold():
    """When both semantic and lexical scores are low, hybrid_search abstains."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "alpha beta", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    ci = ContentIndex()
    engine = GraphQueryEngine(g, index=ci, semantic_index=si, embedding=emb)

    # Query "zeta" — no lexical match, low semantic score.
    # With abstain_threshold=0.5, should abstain (return []).
    results = engine.hybrid_search("zeta", top_k=5, abstain_threshold=0.5)
    assert results == []


def test_hybrid_search_zero_regression_no_threshold():
    """Without abstain_threshold, hybrid_search returns RRF results."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", "alpha beta", {})
    emb = MockEmbeddingAdapter()
    si = SemanticIndex()
    si.add("A.md", emb.embed("alpha beta"))
    ci = ContentIndex()
    ci.index_file("A.md", "alpha beta")
    engine = GraphQueryEngine(g, index=ci, semantic_index=si, embedding=emb)

    results = engine.hybrid_search("alpha", top_k=5)
    assert isinstance(results, list)
    # Should return at least the matching node.
    assert len(results) > 0
