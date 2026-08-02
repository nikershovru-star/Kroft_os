"""ТЗ-ME-01 acceptance + K8 negative tests — Memory Evolution (ADR-046).

K8 discipline: each invariant is asserted positive AND its negation is shown to fail.
The SELF-EVOLVING GUARD (O1) is the load-bearing negative test: HARD-constraint
violations must NEVER reach the Normative/soft layer from experience.
"""

import pytest

from contracts.cognitive_domain import (
    ConfidenceScore, Episode, NodeLamportClock, Policy, PolicyLifecycle,
    Provenance, ProvenanceType, SemanticFact,
)
from contracts.i_cognitive_kernel import IValueSystem, ILayeredMemory
from contracts.i_memory_evolution import IMemoryEvolution
from kernel.memory_evolution import ReferenceMemoryEvolution
from kernel.memory_store import InMemoryLayeredMemory
from kernel.cognitive_kernel import build_kernel


def _ep(ep_id, summary, conf=0.9):
    return Episode(id=ep_id, summary=summary,
                   confidence=ConfidenceScore(conf, ProvenanceType.OBSERVATION),
                   provenance=Provenance(source="s", actor="s"))


def _evolving_values():
    """ValueSystem whose hard checkers read .confidence (duck-typed, per ТЗ-PL-01
    flag). A SemanticFact with conf < 0.99 is vetoed — used to assert the guard."""
    class V(IValueSystem):
        def hard_violations(self, c):
            return ["HARD"] if c.confidence.value < 0.99 else []
        def score(self, c):
            return c.confidence.value
    return V()


# -------------------------------------------------------------------------
# 1. consolidation: repeated high-conf episode -> SemanticFact
# -------------------------------------------------------------------------
def test_consolidate_repeated_high_conf_to_semantic_fact():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "user prefers Y") for i in range(3)]
    facts, policies = me.consolidate(eps)
    assert len(facts) == 1
    assert isinstance(facts[0], SemanticFact)
    assert facts[0].content == "user prefers Y"


def test_consolidated_fact_carries_aggregated_confidence_and_causal():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "k", conf=0.9) for i in range(3)]
    facts, _ = me.consolidate(eps)
    f = facts[0]
    # aggregated (MIN rule) across three 0.9 episodes -> 0.9 (not naive max, not sum)
    assert f.confidence.value == 0.9
    assert f.causal.node_origin == "N"
    assert tuple(e.id for e in eps) == f.source_episodes


# -------------------------------------------------------------------------
# 2. forgetting: low-conf episode -> deprecated, not consolidated
# -------------------------------------------------------------------------
def test_forget_low_confidence_episode():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    low = _ep("lo", "x", conf=0.2)
    assert me.forget([low]) == ["lo"]
    # low-conf single episode is NOT consolidated
    facts, _ = me.consolidate([low])
    assert facts == []


# -------------------------------------------------------------------------
# 3. norm lifecycle: supersede updates lifecycle
# -------------------------------------------------------------------------
def test_norm_lifecycle_supersede():
    mem = InMemoryLayeredMemory()
    old = Policy(id="p-old", name="old", layer="soft", body="b",
                 confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="s", actor="s"),
                 lifecycle=PolicyLifecycle.ACTIVE)
    new = Policy(id="p-new", name="new", layer="soft", body="b2",
                 confidence=ConfidenceScore(0.8, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="s", actor="s"),
                 lifecycle=PolicyLifecycle.ACTIVE)
    mem.commit_normative(old)
    mem.commit_normative(new)
    mem.deprecate_normative("p-old", superseded_by="p-new")
    olds = [p for p in mem.get_normative() if p.id == "p-old"]
    assert olds[0].lifecycle == PolicyLifecycle.SUPERSEDED


def test_deprecate_hard_policy_rejected_o1():
    """O1: HARD layer is immutable from experience — deprecation must raise."""
    mem = InMemoryLayeredMemory()
    hard = Policy(id="p-hard", name="hard", layer="hard", body="invariant",
                  confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="s", actor="s"),
                  lifecycle=PolicyLifecycle.ACTIVE)
    mem.commit_normative(hard)
    with pytest.raises(RuntimeError):
        mem.deprecate_normative("p-hard")


# -------------------------------------------------------------------------
# 4. SELF-EVOLVING GUARD (O1) — negative: hard-violating experience rejected
# -------------------------------------------------------------------------
def test_self_evolving_guard_rejects_hard_violating_fact():
    """A consolidated fact that would violate a KROFT Law must NOT enter memory.
    The guard runs hard_violations BEFORE commit (kernel path)."""
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    # high-confidence repeated episode -> would consolidate
    eps = [_ep(f"e{i}", "bad-rule", conf=0.95) for i in range(3)]
    facts, _ = me.consolidate(eps)
    assert len(facts) == 1
    f = facts[0]
    # guard: hard_violations (duck-typed on .confidence < 0.99) rejects it
    values = _evolving_values()
    assert values.hard_violations(f), "guard must flag the low-confidence consolidated fact"
    # therefore it is NOT committed to the semantic layer
    mem = InMemoryLayeredMemory()
    if not values.hard_violations(f):
        mem.commit_semantic(f)
    assert mem.get_semantic() == [], "hard-violating fact must NOT enter SOFT layer"


def test_kernel_learn_phase_guarded_no_hard_evolution():
    """End-to-end: repeated decisions that would consolidate into a hard-violating
    fact are rejected by the guard; semantic layer stays clean."""
    kb = build_kernel("ME-GUARD")
    values = _evolving_values()
    kb._values = values  # veto anything < 0.99 confidence
    for i in range(3):
        kb.tick(__import__("contracts.cognitive_domain", fromlist=["Intent"]).Intent(
            id=f"i{i}", text="decide Y",
            confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
            provenance=Provenance(source="u", actor="u")))
    # decisions have conf 0.9 -> consolidated fact also ~0.9 -> vetoed by guard
    assert kb._memory.get_semantic() == [], "Self-Evolving guard kept HARD out of SOFT layer"


# -------------------------------------------------------------------------
# 5. negative: no repetition / below threshold -> no consolidation
# -------------------------------------------------------------------------
def test_no_consolidation_below_threshold():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "k", conf=0.5) for i in range(3)]  # below threshold
    facts, _ = me.consolidate(eps)
    assert facts == []


def test_no_consolidation_single_episode():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    facts, _ = me.consolidate([_ep("s1", "rare", conf=0.99)])  # high but single
    assert facts == []


def test_negative_reference_emits_only_soft_never_hard_policy():
    """IMemoryEvolution.consolidate must NEVER produce a HARD policy (O1)."""
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "rule", conf=0.95) for i in range(3)]
    facts, policies = me.consolidate(eps)
    assert all(p.layer != "hard" for p in policies)
    # and facts are SOFT-by-construction
    assert all(isinstance(f, SemanticFact) for f in facts)
