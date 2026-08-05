"""Stage 21 - Query Language tests (9).

GraphQueryEngine.search() now supports a mini-DSL combining full-text
(ContentIndex) AND-search with structural graph filters (tag:, from:, to:,
is:orphan). All conditions are ANDed. Unknown filter keys are ignored.

Regression note: plain text queries behave exactly as in Stage 18.
"""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder, InMemoryEventBus
from services import ContentIndex, GraphQueryEngine


@pytest.fixture
def engine():
    g = InMemoryGraphBuilder()
    bus = InMemoryEventBus()
    ix = ContentIndex()
    # Seed graph + index.
    g.add_node("A.md", label="A", meta={"tags": ["todo", "python"]})
    g.add_node("B.md", label="B", meta={"tags": ["python"]})
    g.add_node("C.md", label="C", meta={"tags": []})  # orphan
    g.add_node("D.md", label="D", meta={"tags": ["todo"]})
    g.add_edge("A.md", "B.md", "links_to")
    g.add_edge("A.md", "C.md", "links_to")
    # Index text.
    ix.index_file("A.md", "python testing guide")
    ix.index_file("B.md", "python cooking blog")
    ix.index_file("C.md", "rust performance")
    ix.index_file("D.md", "testing kitchen")
    return GraphQueryEngine(g, index=ix)


def test_search_pure_text_regression(engine):
    """Stage-18 behavior preserved: plain text search works."""
    assert set(engine.search("python")) == {"A.md", "B.md"}


def test_search_tag_filter(engine):
    """tag:todo intersects with text 'python' -> only A.md."""
    assert engine.search("tag:todo python") == ["A.md"]


def test_search_from_filter(engine):
    """from:A.md returns nodes A links to: B.md, C.md."""
    assert set(engine.search("from:A.md")) == {"B.md", "C.md"}


def test_search_to_filter(engine):
    """to:C.md returns nodes that link TO C.md: A.md (A -> C)."""
    assert engine.search("to:C.md") == ["A.md"]


def test_search_is_orphan(engine):
    """is:orphan returns D.md (the only zero-degree node: A->B, A->C leave
    A/B/C with edges; D.md has none)."""
    assert engine.search("is:orphan") == ["D.md"]


def test_search_multiple_filters(engine):
    """tag:python from:A.md -> B.md (A links to B, B has tag python)."""
    assert engine.search("tag:python from:A.md") == ["B.md"]


def test_search_no_text_only_filter(engine):
    """Only filter, no text tokens -> scan all nodes."""
    assert set(engine.search("tag:todo")) == {"A.md", "D.md"}


def test_search_filter_excludes_all(engine):
    """Text hits A.md+B.md, but tag:nonexistent excludes both -> []."""
    assert engine.search("python tag:nonexistent") == []


def test_search_case_insensitive_tag(engine):
    """tag:TODO matches tag:todo."""
    assert engine.search("tag:TODO") == ["A.md", "D.md"]


def test_search_unknown_filter_ignored(engine):
    """Unknown filter key is ignored (zero regression)."""
    assert set(engine.search("python unknown:xyz")) == {"A.md", "B.md"}


def test_search_empty_query_returns_empty(engine):
    """No text, no filter -> nothing to match (deterministic [])."""
    assert engine.search("") == []


def test_search_filter_only_works_without_index():
    """Filter-only query works even with index=None (collision-safe path)."""
    g = InMemoryGraphBuilder()
    g.add_node("A.md", label="A", meta={"tags": ["todo"]})
    g.add_node("B.md", label="B", meta={"tags": ["python"]})
    g.add_node("E.md", label="E", meta={})  # true orphan (no edges)
    g.add_edge("A.md", "B.md", "links_to")
    engine = GraphQueryEngine(g)  # index=None
    # is:orphan scans the graph directly (no index needed) -> E.md.
    assert engine.search("is:orphan") == ["E.md"]
    # text-only with no index -> [] (Stage-18 zero regression).
    assert engine.search("python") == []
