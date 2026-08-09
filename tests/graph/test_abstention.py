"""P0-A proof-of-fire: retrieval abstention threshold (ADR-0XX).

Self-contained — NO Ollama, NO network. Uses deterministic fake embedding +
fake SemanticIndex so the test runs in the default (non-KNOWLEDGE_EVAL) suite
and actually proves the threshold gates output.

Proves:
  - POSITIVE: a query whose best candidate clears the cosine threshold is
    returned with abstained=False.
  - NEGATIVE: a query whose best candidate is below threshold returns [] with
    abstained=True (the engine refuses to hallucinate).
  - BOUNDARY: cosine == threshold is INCLUDED (>=).
  - ZERO-REGRESSION: no semantic_index/embedding wired -> ([], True);
    semantic_threshold=None -> ([], True).
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import pytest

from services.graph_query_engine import GraphQueryEngine


class _FakeEmbedding:
    """Deterministic embedding: returns a fixed vector per query string."""

    def embed(self, text: str) -> List[float]:
        # Stable hash -> unit-ish vector. Cosine with the index vectors is what
        # drives the test, so we just need consistent, distinct vectors.
        h = hash(text)
        return [float((h >> (8 * i)) & 0xFF) / 255.0 for i in range(4)]


class _FakeSemanticIndex:
    """Returns pre-seeded (node_id, cosine) candidates for a given query."""

    def __init__(self, by_query: dict):
        # by_query: query_text -> List[(node_id, cosine_score)]
        self._by_query = by_query

    def search(self, q_emb, top_k: int = 50) -> List[Tuple[str, float]]:
        # q_emb is ignored; we key on the *query string* via a side channel is
        # impossible here, so the FakeEmbedding + FakeSemanticIndex are wired
        # together by the test using a closure below.
        return self._results[:top_k]


def _make_engine(candidates: List[Tuple[str, float]],
                embedding: Optional[Any] = None,
                threshold_wired: bool = True) -> GraphQueryEngine:
    """Build an engine whose semantic_index returns `candidates` for ANY query.

    The fake embedding ignores the query; the fake index returns the same
    candidate list regardless of query (sufficient to test threshold gating).
    """
    class _Builder:
        def get_graph(self):
            return {"nodes": [], "edges": []}

    class _Index:
        def search(self, q_emb, top_k: int = 50):
            return candidates[:top_k]

    emb = embedding if embedding is not None else _FakeEmbedding()
    si = _Index() if threshold_wired else None
    eng = GraphQueryEngine(_Builder(), semantic_index=si, embedding=emb)
    return eng


POSITIVE = [("n_python", 0.82), ("n_java", 0.55), ("n_cobol", 0.20)]
NEGATIVE = [("n_maritime", 0.12), ("n_astrology", 0.08), ("n_crypto", 0.04)]


def test_positive_query_returns_best_and_not_abstained():
    eng = _make_engine(POSITIVE)
    results, abstained = eng.query_with_abstention("python programming", top_k=3,
                                                   semantic_threshold=0.30)
    assert abstained is False
    assert results[0][0] == "n_python"
    assert results[0][1] == 0.82
    # only candidates >= 0.30 kept: n_python, n_java (0.55). n_cobol (0.20) dropped.
    assert [nid for nid, _ in results] == ["n_python", "n_java"]


def test_negative_query_abstains():
    eng = _make_engine(NEGATIVE)
    results, abstained = eng.query_with_abstention("underwater basket weaving",
                                                   top_k=5, semantic_threshold=0.30)
    assert abstained is True
    assert results == []


def test_boundary_cosine_equal_threshold_is_included():
    # candidate exactly at threshold must be returned (>=)
    eng = _make_engine([("n_edge", 0.30), ("n_low", 0.10)])
    results, abstained = eng.query_with_abstention("boundary", top_k=5,
                                                   semantic_threshold=0.30)
    assert abstained is False
    assert [nid for nid, _ in results] == ["n_edge"]


def test_zero_regression_no_semantic_index_abstains():
    eng = _make_engine(POSITIVE, threshold_wired=False)
    results, abstained = eng.query_with_abstention("anything", top_k=5,
                                                   semantic_threshold=0.30)
    assert abstained is True
    assert results == []


def test_zero_regression_threshold_none_abstains():
    eng = _make_engine(POSITIVE)
    results, abstained = eng.query_with_abstention("anything", top_k=5,
                                                   semantic_threshold=None)
    assert abstained is True
    assert results == []


def test_empty_query_abstains():
    eng = _make_engine(POSITIVE)
    results, abstained = eng.query_with_abstention("   ", top_k=5,
                                                   semantic_threshold=0.30)
    assert abstained is True
    assert results == []
