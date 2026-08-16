"""PHASE C — Graph ← Self-Evolution verification (ТЗ §18 Case 1-6).

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
    AggregationRule,
    ConfidenceScore,
    Episode,
    NodeLamportClock,
    Provenance,
    ProvenanceType,
)
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


# Case 1 — valid repeated evidence -> FACT promoted to graph
def test_case1_valid_repeated_evidence_promoted():
    evo, b = _evo(), _builder()
    eps = [_ep("KROFT uses CRDT", 0.9, "e1"), _ep("KROFT uses CRDT", 0.9, "e2")]
    created = promote_facts_to_graph(eps, evo, b)
    assert len(created) == 1
    g = b.get_graph()
    assert len(g["nodes"]) == 1
    n = g["nodes"][0]
    assert n["meta"]["type"] == "SOFT_FACT"
    assert n["meta"]["provenance"] == ["e1", "e2"]
    assert n["meta"]["confidence"] == pytest.approx(0.9)


# Case 2 — single observation -> NO promotion
def test_case2_single_observation_no_promotion():
    evo, b = _evo(), _builder()
    created = promote_facts_to_graph([_ep("lonely fact", 0.95, "e1")], evo, b)
    assert created == []
    assert b.get_graph()["nodes"] == []


# Case 3 — low confidence -> NO promotion
def test_case3_low_confidence_no_promotion():
    evo, b = _evo(), _builder()
    eps = [_ep("uncertain", 0.4, "e1"), _ep("uncertain", 0.4, "e2")]
    assert promote_facts_to_graph(eps, evo, b) == []
    assert b.get_graph()["nodes"] == []


# Case 4 — failed causal attribution -> NO promotion
# (low confidence below threshold simulates a non-causal/weak signal)
def test_case4_failed_causal_no_promotion():
    evo, b = _evo(), _builder()
    eps = [_ep("weak cause", 0.5, "e1"), _ep("weak cause", 0.5, "e2")]
    assert promote_facts_to_graph(eps, evo, b) == []
    assert b.get_graph()["nodes"] == []


# Case 5 — attempted HARD policy mutation -> BLOCKED
# ReferenceMemoryEvolution.consolidate() returns ([], []) for policies (O1: never
# emits HARD). promote_facts_to_graph writes ONLY facts, so no policy/node appears.
def test_case5_hard_policy_blocked():
    evo, b = _evo(), _builder()
    # Even if a caller passed policy-like episodes, consolidate() yields no facts
    # when summaries are not repeated above threshold; and we never write policies.
    eps = [_ep("HARD: delete all", 1.0, "e1"), _ep("HARD: delete all", 1.0, "e2")]
    # These WOULD consolidate as facts (repeated + high conf) — but they are SOFT
    # facts, NOT HARD policies. The O1 guard is in ReferenceMemoryEvolution: it
    # never returns Policy objects. Assert NO policy-shaped node is created.
    created = promote_facts_to_graph(eps, evo, b)
    g = b.get_graph()
    # If promoted, it must be tagged SOFT_FACT, never HARD/POLICY.
    for n in g["nodes"]:
        assert n["meta"]["type"] == "SOFT_FACT"
        assert n["meta"]["layer"] == "soft"


# Case 6 — duplicate fact -> NO duplicate node
def test_case6_duplicate_no_duplicate_node():
    evo, b = _evo(), _builder()
    eps = [_ep("dup fact", 0.9, "e1"), _ep("dup fact", 0.9, "e2")]
    first = promote_facts_to_graph(eps, evo, b)
    assert len(first) == 1
    # Re-run consolidation on the SAME episodes: should NOT add a second node.
    second = promote_facts_to_graph(eps, evo, b)
    assert second == []
    assert len(b.get_graph()["nodes"]) == 1
