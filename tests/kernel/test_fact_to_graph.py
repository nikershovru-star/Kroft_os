"""PHASE C + PHASE B.3 — Graph <- Self-Evolution + Multi-Resolution ladder.

Fast, deterministic: reuses ReferenceMemoryEvolution (real consolidation gate)
+ InMemoryGraphBuilder (real IGraphBuilder). No production snapshot, no LLM.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.cognitive_domain import (  # noqa: E402
    ConfidenceScore,
    Episode,
    NodeLamportClock,
    Provenance,
    ProvenanceType,
)
from contracts.knowledge_graph import NodeType  # noqa: E402
from infrastructure.graph_builder import InMemoryGraphBuilder  # noqa: E402
from kernel.memory_evolution import ReferenceMemoryEvolution  # noqa: E402
from kernel.fact_to_graph import promote_facts_to_graph  # noqa: E402


def _ep(summary: str, conf: float, eid: str) -> Episode:
    return Episode(
        id=eid,
        summary=summary,
        confidence=ConfidenceScore(conf, ProvenanceType.OBSERVATION),
        provenance=Provenance("observation", "local"),
    )


def _evo() -> ReferenceMemoryEvolution:
    return ReferenceMemoryEvolution(
        clock=NodeLamportClock("local"), confidence_threshold=0.7, min_repetitions=2
    )


def _builder() -> InMemoryGraphBuilder:
    return InMemoryGraphBuilder()


# --- PHASE C: FACT promotion (ТЗ §18 Case 1-6) ---

def test_case1_valid_repeated_evidence_promoted():
    evo, b = _evo(), _builder()
    eps = [_ep("KROFT uses CRDT", 0.9, "e1"), _ep("KROFT uses CRDT", 0.9, "e2")]
    res = promote_facts_to_graph(eps, evo, b)
    assert len(res["facts"]) == 1
    n = b.get_graph()["nodes"][0]
    assert n["meta"]["type"] == NodeType.FACT.value
    assert n["meta"]["level"] == "fact"
    assert n["meta"]["provenance"] == ["e1", "e2"]


def test_case2_single_observation_no_promotion():
    evo, b = _evo(), _builder()
    res = promote_facts_to_graph([_ep("lonely fact", 0.95, "e1")], evo, b)
    assert res["facts"] == []
    assert b.get_graph()["nodes"] == []


def test_case3_low_confidence_no_promotion():
    evo, b = _evo(), _builder()
    eps = [_ep("uncertain", 0.4, "e1"), _ep("uncertain", 0.4, "e2")]
    assert promote_facts_to_graph(eps, evo, b)["facts"] == []
    assert b.get_graph()["nodes"] == []


def test_case4_failed_causal_no_promotion():
    evo, b = _evo(), _builder()
    eps = [_ep("weak cause", 0.5, "e1"), _ep("weak cause", 0.5, "e2")]
    assert promote_facts_to_graph(eps, evo, b)["facts"] == []
    assert b.get_graph()["nodes"] == []


def test_case5_hard_policy_blocked():
    evo, b = _evo(), _builder()
    eps = [_ep("HARD: delete all", 1.0, "e1"), _ep("HARD: delete all", 1.0, "e2")]
    res = promote_facts_to_graph(eps, evo, b)
    g = b.get_graph()
    for n in g["nodes"]:
        assert n["meta"]["type"] == NodeType.FACT.value  # SOFT fact, never HARD
        assert n["meta"]["layer"] == "soft"


def test_case6_duplicate_no_duplicate_node():
    evo, b = _evo(), _builder()
    eps = [_ep("dup fact", 0.9, "e1"), _ep("dup fact", 0.9, "e2")]
    first = promote_facts_to_graph(eps, evo, b)
    assert len(first["facts"]) == 1
    second = promote_facts_to_graph(eps, evo, b)
    assert second["facts"] == []
    assert len(b.get_graph()["nodes"]) == 1


# --- PHASE B.3: ladder (FACT -> PATTERN -> CONCEPT) ---

def test_pattern_created_from_two_facts_same_keyword():
    evo, b = _evo(), _builder()
    # Two DISTINCT repeated summaries sharing the leading keyword "kroft uses crdt".
    eps = [
        _ep("kroft uses CRDT for sync", 0.9, "e1"),
        _ep("kroft uses CRDT for sync", 0.9, "e2"),
        _ep("kroft uses CRDT for state", 0.9, "e3"),
        _ep("kroft uses CRDT for state", 0.9, "e4"),
    ]
    res = promote_facts_to_graph(eps, evo, b)
    assert len(res["facts"]) == 2  # two distinct consolidated facts
    assert len(res["patterns"]) == 1  # both share keyword "kroft uses crdt"
    pid = res["patterns"][0]
    edges = b.get_graph()["edges"]
    assert any(e["from"] in res["facts"] and e["to"] == pid and e["relation"] == "aggregates"
               for e in edges)


def test_concept_created_from_two_patterns():
    evo, b = _evo(), _builder()
    # Two keyword-groups, each >=2 repeated facts, sharing leading token "kroft".
    eps = [
        _ep("kroft uses CRDT sync", 0.9, "e1"),
        _ep("kroft uses CRDT sync", 0.9, "e2"),
        _ep("kroft uses CRDT state", 0.9, "e3"),
        _ep("kroft uses CRDT state", 0.9, "e4"),
        _ep("kroft stores VEC vault", 0.9, "e5"),
        _ep("kroft stores VEC vault", 0.9, "e6"),
        _ep("kroft stores VEC obsidian", 0.9, "e7"),
        _ep("kroft stores VEC obsidian", 0.9, "e8"),
    ]
    res = promote_facts_to_graph(eps, evo, b)
    assert len(res["facts"]) == 4
    assert len(res["patterns"]) == 2  # "kroft uses crdt" + "kroft stores vec"
    assert len(res["concepts"]) == 1   # both patterns share token "kroft"
    cid = res["concepts"][0]
    edges = b.get_graph()["edges"]
    assert any(e["from"] in res["patterns"] and e["to"] == cid and e["relation"] == "summarizes"
               for e in edges)


def test_ladder_queryable_via_graph_query_engine():
    from services.graph_query_engine import GraphQueryEngine  # noqa: E402
    from services.multi_resolution import MultiResolutionQuery  # noqa: E402
    evo, b = _evo(), _builder()
    eps = [
        _ep("kroft uses CRDT sync", 0.9, "e1"),
        _ep("kroft uses CRDT sync", 0.9, "e2"),
        _ep("kroft uses CRDT state", 0.9, "e3"),
        _ep("kroft uses CRDT state", 0.9, "e4"),
    ]
    res = promote_facts_to_graph(eps, evo, b)
    mr = MultiResolutionQuery(GraphQueryEngine(b), b)
    assert set(mr.nodes_by_level("fact")) == set(res["facts"])
    assert set(mr.nodes_by_level("pattern")) == set(res["patterns"])
    pid = res["patterns"][0]
    zoomed = mr.zoom_in(pid)
    assert set(zoomed) == set(res["facts"])
    fid = res["facts"][0]
    assert mr.zoom_out(fid) == [pid]
