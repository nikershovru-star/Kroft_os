"""K8 tests for ТЗ-SEARCH-01 — deterministic knowledge retrieval (LLM-free).

Covers (acceptance + O1/K1/K6/K8 + ADR-069 + reviewer flags A–D):
- search returns relevant hits from semantic facts / graph nodes.
- ranking is a TOTAL order (confidence desc, relevance desc, id asc) -> deterministic.
- scope filters the layer (semantic/episodic/normative/graph/all).
- negative: empty/short-token query -> []; no match -> []; unknown scope -> [].
- determinism: repeated identical query -> identical ordered result (I-09).
- O1: search is read-only (does not mutate memory/graph).
- existing content_index / knowledge graph tests remain green (run separately).

Флаг A: no shared-index mutation — ReferenceSearchService pure-scans memory/graph.
Флаг C: standalone service, no build_kernel wiring.
Флаг D: SearchHit.causal is real Optional[CausalMark] (None for graph/episode/policy).
"""

from __future__ import annotations

from contracts.cognitive_domain import (
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
    SemanticFact,
)
from contracts.i_search import ISearchService, SearchHit, SearchScope
from contracts.knowledge_graph import Node, NodeType
from kernel.memory_store import InMemoryLayeredMemory
from kernel.search import ReferenceSearchService, build_search_service
from services.knowledge_graph.engine import InMemoryGraphEngine


def _memory_with_facts():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("S")
    mem.commit_semantic(SemanticFact(
        id="sf-blue", content="choose blue when sky is clear",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    mem.commit_semantic(SemanticFact(
        id="sf-red", content="avoid red because it fails often",
        confidence=ConfidenceScore(0.6, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    return mem


def _graph():
    g = InMemoryGraphEngine()
    g.add_node(Node(id="adr65", type=NodeType.ADR,
                    label="ADR-065 llm advisor boundary"))
    g.add_node(Node(id="adr54", type=NodeType.ADR,
                    label="ADR-054 confidence score contract"))
    return g


# ---------------------------------------------------------------------------
# 1. search returns relevant hits (semantic + graph)
# ---------------------------------------------------------------------------
def test_search_semantic_returns_relevant_hit():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hits = svc.search("choose blue", scope=SearchScope.ALL)
    assert any(h.source == "semantic:sf-blue" for h in hits)


def test_search_graph_returns_node_hit():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hits = svc.search("ADR confidence", scope=SearchScope.GRAPH)
    sources = [h.source for h in hits]
    assert "graph:adr54" in sources


# ---------------------------------------------------------------------------
# 2. ranking is TOTAL order (confidence desc, relevance desc, id asc)
# ---------------------------------------------------------------------------
def test_ranking_by_confidence_total_order():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    # query touches BOTH facts (blue in sf-blue, red in sf-red); equal relevance ->
    # confidence must decide the order (0.9 sf-blue > 0.6 sf-red)
    hits = svc.search("blue red", scope=SearchScope.ALL)
    ranked = [h for h in hits if h.hit_type == "semantic"]
    assert len(ranked) == 2
    assert ranked[0].source == "semantic:sf-blue"
    assert ranked[0].confidence.value > ranked[1].confidence.value


def test_ranking_is_total_order_deterministic_tiebreak():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("T")
    mem.commit_semantic(SemanticFact(id="zzz", content="token alpha",
        confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION), causal=clk.tick(), source_episodes=()))
    mem.commit_semantic(SemanticFact(id="aaa", content="token alpha",
        confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION), causal=clk.tick(), source_episodes=()))
    svc = ReferenceSearchService(mem, None)
    hits = svc.search("token alpha", scope=SearchScope.SEMANTIC)
    assert [h.source for h in hits] == ["semantic:aaa", "semantic:zzz"]


# ---------------------------------------------------------------------------
# 3. scope filters the layer
# ---------------------------------------------------------------------------
def test_scope_semantic_only_excludes_graph():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hits = svc.search("ADR", scope=SearchScope.SEMANTIC)
    assert all(h.hit_type == "semantic" for h in hits)
    assert all("graph:" not in h.source for h in hits)


def test_scope_graph_only_excludes_semantic():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hits = svc.search("ADR", scope=SearchScope.GRAPH)
    assert all(h.hit_type == "graph" for h in hits)


def test_scope_unknown_returns_empty():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hits = svc.search("choose", scope="nonexistent")
    assert hits == []


# ---------------------------------------------------------------------------
# 4. negative: empty / no-match / short-token -> []
# ---------------------------------------------------------------------------
def test_empty_query_returns_empty():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    assert svc.search("") == []
    assert svc.search("!!! ---") == []


def test_no_match_returns_empty():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    assert svc.search("zzznonexistentzzz") == []


def test_top_k_limits_results():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("K")
    for i in range(10):
        mem.commit_semantic(SemanticFact(id=f"sf{i}", content=f"alpha beta gamma {i}",
            confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION), causal=clk.tick(), source_episodes=()))
    svc = ReferenceSearchService(mem, None)
    hits = svc.search("alpha beta gamma", scope=SearchScope.SEMANTIC, top_k=3)
    assert len(hits) == 3


# ---------------------------------------------------------------------------
# 5. determinism: repeated identical query -> identical ordered result (I-09)
# ---------------------------------------------------------------------------
def test_determinism_repeated_query():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    a = svc.search("choose blue", scope=SearchScope.ALL)
    b = svc.search("choose blue", scope=SearchScope.ALL)
    c = svc.search("choose blue", scope=SearchScope.ALL)
    assert [h.source for h in a] == [h.source for h in b] == [h.source for h in c]


# ---------------------------------------------------------------------------
# 6. O1: read-only — search does not mutate memory or graph
# ---------------------------------------------------------------------------
def test_search_is_read_only():
    mem = _memory_with_facts()
    g = _graph()
    before_sem = len(mem.get_semantic())
    before_nodes = len(g.nodes())
    svc = ReferenceSearchService(mem, g)
    svc.search("choose blue", scope=SearchScope.ALL)
    svc.search("ADR", scope=SearchScope.GRAPH)
    assert len(mem.get_semantic()) == before_sem
    assert len(g.nodes()) == before_nodes


def test_search_hit_causal_real_type():
    svc = ReferenceSearchService(_memory_with_facts(), _graph())
    hit = svc.search("choose blue", scope=SearchScope.SEMANTIC)[0]
    assert hit.causal is not None
    ghit = svc.search("ADR", scope=SearchScope.GRAPH)[0]
    assert ghit.causal is None


# ---------------------------------------------------------------------------
# 7. factory + port conformance
# ---------------------------------------------------------------------------
def test_factory_builds_standalone_service():
    svc = build_search_service(_memory_with_facts(), _graph())
    assert isinstance(svc, ISearchService)
    assert isinstance(svc, ReferenceSearchService)
    assert svc.search("choose blue")
