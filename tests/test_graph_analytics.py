"""Stage 26 - Graph Analytics tests (8).

GraphQueryEngine gains centrality() (degree), connected_components() (weak,
BFS) and pagerank() (iterative, stdlib-only). The HTTP server exposes them
at /api/stats/{centrality,components,pagerank}.

NOTE: get_graph() returns nodes as a LIST of node dicts — the analytics
methods iterate n["id"], never nodes.keys() (that is the on-disk snapshot
shape, a known collision from Stage 27's verifier).
"""
from __future__ import annotations

import http.client
import json
import socket
import time

import pytest

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from services import GraphQueryEngine, ContentIndex
from adapters.http_server import KnowledgeOSServer


def _engine(edges=(), nodes=()):
    g = InMemoryGraphBuilder()
    for n in nodes:
        g.add_node(n, n, {})
    for src, dst in edges:
        g.add_edge(src, dst, "links_to")
    return GraphQueryEngine(g), g


# ----- centrality -----
def test_centrality_empty():
    e, _ = _engine()
    assert e.centrality() == {}


def test_centrality_star():
    e, _ = _engine(nodes="ABCD", edges=[("A", "B"), ("A", "C"), ("A", "D")])
    c = e.centrality()
    assert c["A"] == {"in": 0, "out": 3, "total": 3}
    for leaf in "BCD":
        assert c[leaf] == {"in": 1, "out": 0, "total": 1}


# ----- components -----
def test_components_empty():
    e, _ = _engine()
    assert e.connected_components() == []


def test_components_two_clusters():
    e, _ = _engine(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")],
    )
    comps = e.connected_components()
    assert comps == [["A", "B"], ["C", "D"]]


# ----- pagerank -----
def test_pagerank_empty():
    e, _ = _engine()
    assert e.pagerank() == {}


def test_pagerank_converges():
    # 2-cycle A<->B: symmetric graph -> equal scores, sum == 1.
    e, _ = _engine(nodes="AB", edges=[("A", "B"), ("B", "A")])
    pr = e.pagerank()
    assert pr["A"] == pytest.approx(pr["B"])
    assert pr["A"] == pytest.approx(0.5)
    assert sum(pr.values()) == pytest.approx(1.0)


def test_pagerank_dangling():
    # B has no outgoing edges (dangling) — must not crash; mass conserved.
    e, _ = _engine(nodes="AB", edges=[("A", "B")])
    pr = e.pagerank()
    assert sum(pr.values()) == pytest.approx(1.0)
    # B receives A's link AND its own dangling redistribution -> B > A.
    assert pr["B"] > pr["A"] > 0.0


# ----- HTTP API -----
def _wait_ready(host, port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"server on {host}:{port} never came up")


def test_api_stats_endpoints():
    c = DependencyContainer()
    g = InMemoryGraphBuilder()
    for n in "AB":
        g.add_node(n, n, {})
    g.add_edge("A", "B", "links_to")
    c.register_instance("IGraphBuilder", g)
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_instance("ContentIndex", ContentIndex())
    c.register_factory("GraphQueryEngine", lambda: GraphQueryEngine(g))
    server = KnowledgeOSServer(c, host="127.0.0.1", port=0)
    server.start()
    try:
        _wait_ready("127.0.0.1", server.port)
        results = {}
        for name in ("centrality", "components", "pagerank"):
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            conn.request("GET", f"/api/stats/{name}")
            r = conn.getresponse()
            assert r.status == 200
            assert "application/json" in r.getheader("Content-Type", "")
            results[name] = json.loads(r.read().decode("utf-8"))
        assert results["centrality"]["A"] == {"in": 0, "out": 1, "total": 1}
        assert results["components"] == [["A", "B"]]
        assert set(results["pagerank"].keys()) == {"A", "B"}
        assert sum(results["pagerank"].values()) == pytest.approx(1.0)
    finally:
        server.stop()
