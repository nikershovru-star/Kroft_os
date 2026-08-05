"""Stage 20 - Fuzzy Search & Prefix Suggestion tests (10).

ContentIndex.suggest / fuzzy_search + GraphQueryEngine proxy + zero regression.
"""
import pytest
from services import ContentIndex, GraphQueryEngine
from infrastructure import InMemoryGraphBuilder


def test_suggest_prefix_basic():
    ix = ContentIndex()
    ix.index_file("A.md", "python architecture")
    ix.index_file("B.md", "pythonic patterns")
    assert ix.suggest("py") == ["python", "pythonic"]
    # 'pythonic' also starts with 'python', so prefix-suggest keeps both.
    # Use distinct roots to prove narrowing works:
    assert ix.suggest("arch") == ["architecture"]   # only A.md's term
    assert ix.suggest("pat") == ["patterns"]        # only B.md's term
    assert ix.suggest("z") == []


def test_suggest_limit():
    ix = ContentIndex()
    for i in range(20):
        ix.index_file(f"{i}.md", f"term{i} stuff")
    assert len(ix.suggest("term", limit=5)) == 5


def test_suggest_after_remove():
    ix = ContentIndex()
    ix.index_file("A.md", "python guide")
    ix.remove_file("A.md")
    assert ix.suggest("py") == []


def test_fuzzy_single_token():
    ix = ContentIndex()
    ix.index_file("A.md", "python testing")
    assert ix.fuzzy_search("pithon") == ["A.md"]


def test_fuzzy_multiple_tokens():
    ix = ContentIndex()
    ix.index_file("A.md", "python testing guide")
    ix.index_file("B.md", "python cooking")
    # 'pithon' ~ 'python', 'testng' ~ 'testing'
    assert ix.fuzzy_search("pithon testng") == ["A.md"]


def test_fuzzy_cutoff_too_strict():
    ix = ContentIndex()
    ix.index_file("A.md", "python")
    # 'qzx' shares no resemblance with 'python' -> ratio < 0.1 cutoff
    assert ix.fuzzy_search("qzx", cutoff=0.1) == []


def test_fuzzy_and_logic():
    ix = ContentIndex()
    ix.index_file("A.md", "python testing")
    ix.index_file("B.md", "python cooking")
    # 'pithon' matches python, 'testng' matches testing -> only A.md
    assert ix.fuzzy_search("pithon testng") == ["A.md"]


def test_fuzzy_ranking_by_frequency():
    ix = ContentIndex()
    ix.index_file("low.md", "python once")
    ix.index_file("high.md", "python python python")
    # Both match 'pithon', but high.md has more occurrences
    assert ix.fuzzy_search("pithon") == ["high.md", "low.md"]


def test_graph_query_engine_fuzzy_proxy():
    g = InMemoryGraphBuilder()
    ix = ContentIndex()
    ix.index_file("A.md", "python guide")
    engine = GraphQueryEngine(g, index=ix)
    assert engine.fuzzy_search("pithon") == ["A.md"]


def test_graph_query_engine_fuzzy_no_index():
    g = InMemoryGraphBuilder()
    engine = GraphQueryEngine(g, index=None)
    assert engine.fuzzy_search("anything") == []


def test_fuzzy_search_restored_from_snapshot():
    """Stage 19 round-trip keeps _sorted_terms so fuzzy/suggest work cold."""
    ix = ContentIndex()
    ix.index_file("A.md", "python architecture")
    ix.index_file("B.md", "pythonic patterns")
    snap = ix.snapshot()
    cold = ContentIndex()
    cold.restore(snap)
    assert cold.suggest("py") == ["python", "pythonic"]
    # 'pithon' is close to BOTH 'python' (A) and 'pythonic' (B), so both
    # documents match (AND logic across the two fuzzy groups yields the union).
    assert set(cold.fuzzy_search("pithon")) == {"A.md", "B.md"}
