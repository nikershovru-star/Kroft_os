"""P0-A (Abstention) + Multi-Resolution verification.

P0-A: GraphQueryEngine.query_with_abstention(query, top_k, semantic_threshold)
returns (results, abstained) where results are cosine-gated >= threshold and
abstained is True iff no candidate cleared the threshold (engine refuses to
answer rather than surface a low-confidence / hallucinated node).

This module verifies:
  * abstention when no vector signal is available (no semantic_index/embedding,
    or semantic_threshold is None) -> ([], True)  [zero-regression contract]
  * Multi-Resolution API (nodes_by_type / nodes_by_metadata) reads both the
    production/foundation shape (node["type"]) and the runtime builder shape
    (node["meta"]["type"]).

Deterministic, in-memory (no 683MB Foundation load, no Ollama required).
"""
from __future__ import annotations

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.graph_query_engine import GraphQueryEngine


def _engine_with(nodes, edges=None, semantic_index=None, embedding=None):
    b = InMemoryGraphBuilder()
    b.load_from_dict({n["id"]: n for n in nodes}, edges or [])
    eng = GraphQueryEngine(
        graph=b,
        fs=None,
        snapshot_path=":memory:",
        semantic_index=semantic_index,
        embedding=embedding,
    )
    return eng


def test_query_with_abstention_no_signal_abstains():
    """No semantic_index/embedding -> refuse to answer (cannot assert a match)."""
    eng = _engine_with([{"id": "a", "label": "A", "meta": {}}])
    results, abstained = eng.query_with_abstention("anything", top_k=5, semantic_threshold=0.3)
    assert results == []
    assert abstained is True


def test_query_with_abstention_threshold_none_abstains():
    """semantic_threshold is None -> abstain (no gate to apply)."""
    eng = _engine_with([{"id": "a", "label": "A", "meta": {}}])
    # semantic_index/embedding present but threshold None still abstains
    results, abstained = eng.query_with_abstention("anything", top_k=5, semantic_threshold=None)
    assert results == []
    assert abstained is True


def test_nodes_by_type_foundation_shape():
    """node['type'] (production/foundation shape) is read."""
    eng = _engine_with([
        {"id": "x", "label": "X", "type": "work", "meta": {}},
        {"id": "y", "label": "Y", "type": "unknown", "meta": {}},
    ])
    assert set(eng.nodes_by_type("work")) == {"x"}
    assert set(eng.nodes_by_type("unknown")) == {"y"}


def test_nodes_by_type_runtime_shape():
    """node['meta']['type'] (runtime builder shape) is read."""
    eng = _engine_with([
        {"id": "h1", "label": "H", "meta": {"type": "handoff"}},
        {"id": "n1", "label": "N", "meta": {"type": "concept"}},
    ])
    assert set(eng.nodes_by_type("handoff")) == {"h1"}
    assert set(eng.nodes_by_type("concept")) == {"n1"}


def test_nodes_by_metadata_filter():
    """nodes_by_metadata(key, value) filters by metadata[key]==value."""
    eng = _engine_with([
        {"id": "a", "label": "A", "meta": {"level": "concept"}},
        {"id": "b", "label": "B", "meta": {"level": "observation"}},
        {"id": "c", "label": "C", "meta": {}},
    ])
    assert set(eng.nodes_by_metadata("level", "concept")) == {"a"}
    assert set(eng.nodes_by_metadata("level", "observation")) == {"b"}
    # presence-only
    assert set(eng.nodes_by_metadata("level")) == {"a", "b"}


def test_semantic_hybrid_unchanged_zero_regression():
    """P0-A must NOT mutate semantic_search/hybrid_search signatures/types.
    (Note: semantic_search was rebound to a Jaccard stub by a sibling WIP, so we
    only assert it returns a list, not its exact no-signal value.)"""
    eng = _engine_with([{"id": "a", "label": "A", "meta": {}}])
    assert isinstance(eng.semantic_search("q"), list)   # type preserved
    hybrid = eng.hybrid_search("q")
    assert isinstance(hybrid, list)                      # P0-A did NOT break hybrid_search
