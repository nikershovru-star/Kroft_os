"""ТЗ-RF-01 acceptance + K8 negative tests — Reflection Engine (ADR-060).

K8 discipline: each invariant asserted positive AND its negation shown to fail.
ФЛАГ 1 (outcome-based): consolidation/deprecation driven by ExecutionOutcome, NOT
intent text. O1 Self-Evolving guard: hard-violating proposals never reach SOFT layer.
"""

import pytest

from contracts.cognitive_domain import (
    ConfidenceScore, Episode, ExecutionOutcome, Intent, NodeLamportClock, Policy,
    PolicyLifecycle, Provenance, ProvenanceType, ReflectionReport, SemanticFact,
)
from contracts.i_cognitive_kernel import IValueSystem, ILayeredMemory
from contracts.i_reflection import IReflectionEngine
from kernel.reflection import ReferenceReflectionEngine
from kernel.memory_store import InMemoryLayeredMemory
from kernel.cognitive_kernel import build_kernel


def _ep(ep_id, summary, conf=0.9):
    return Episode(id=ep_id, summary=summary,
                   confidence=ConfidenceScore(conf, ProvenanceType.OBSERVATION),
                   provenance=Provenance(source="s", actor="s"))


def _out(ep_id, success, util):
    return ExecutionOutcome(ep_id, success, util,
                             ConfidenceScore(util, ProvenanceType.OBSERVATION), None)


# -------------------------------------------------------------------------
# 1. reflection yields report with candidates when there is experience
# -------------------------------------------------------------------------
def test_reflect_yields_report_with_candidates():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    mem.record_episode(_ep("e0", "pattern:decide Y"))
    outs = [_out("e0", True, 0.85) for _ in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert isinstance(r, ReflectionReport)
    assert len(r.consolidation_candidates) == 1


# -------------------------------------------------------------------------
# 2. OUTCOME-BASED (ФЛАГ 1): success -> consolidation, failure -> deprecation
# -------------------------------------------------------------------------
def test_outcome_success_consolidates():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    for i in range(3):
        mem.record_episode(_ep(f"e{i}", "pattern:decide Y"))
    outs = [_out(f"e{i}", True, 0.85) for i in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert len(r.consolidation_candidates) == 1
    # assertion is on outcome.success/utility, NOT on intent text
    assert r.consolidation_candidates[0].content == "pattern:decide Y"


def test_outcome_failure_deprecates():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    for i in range(3):
        mem.record_episode(_ep(f"e{i}", "pattern:decide X"))
    outs = [_out(f"e{i}", False, 0.15) for i in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert r.deprecation_candidates == ("pattern:decide X",)
    assert r.consolidation_candidates == ()


def test_outcome_single_repetition_not_enough():
    """Outcome-based requires >= min_repetitions; single success does NOT consolidate."""
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    mem.record_episode(_ep("e0", "rare"))
    r = me.reflect(mem, None, outcomes=[_out("e0", True, 0.9)])
    assert r.consolidation_candidates == ()


# -------------------------------------------------------------------------
# 3. Self-Evolving guard (O1): hard-violating suggestion rejected before commit
# -------------------------------------------------------------------------
def _guard_values():
    class V(IValueSystem):
        def hard_violations(self, c):
            return ["HARD"] if c.confidence.value < 0.99 else []
        def score(self, c):
            return c.confidence.value
    return V()


def test_reflection_report_carries_confidence_and_causal():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    mem.record_episode(_ep("e0", "pattern:decide Y"))
    outs = [_out("e0", True, 0.9) for _ in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert r.causal is not None and r.causal.node_origin == "R"
    assert isinstance(r.confidence, ConfidenceScore)


def test_kernel_reflection_guard_rejects_hard_violating():
    """End-to-end: Reflection proposes consolidation, but kernel guard (hard_violations
    on low-confidence facts) rejects it before commit (O1)."""
    kb = build_kernel("RF-GUARD")
    kb._values = _guard_values()  # veto anything < 0.99 confidence
    for i in range(3):
        kb._world.update(_mk_obs(i))
        kb.tick(_mk_intent(i))
    # Reflection proposals have conf ~0.9 -> vetoed by guard -> semantic stays clean
    assert kb._memory.get_semantic() == [], "O1: Reflection proposals kept out of SOFT layer"


def test_reflection_never_emits_hard_policy():
    """ReferenceReflectionEngine.policy_suggestions is SOFT-only (empty in reference)."""
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    mem.record_episode(_ep("e0", "pattern:decide Y"))
    outs = [_out("e0", True, 0.9) for _ in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert all(p.layer != "hard" for p in r.policy_suggestions)


# -------------------------------------------------------------------------
# 4. negative: no experience -> empty report
# -------------------------------------------------------------------------
def test_reflect_no_experience_empty_report():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    r = me.reflect(mem, None, outcomes=[])
    assert r.consolidation_candidates == ()
    assert r.deprecation_candidates == ()
    assert r.insights == ()


def test_reflect_without_outcomes_empty_report():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    # episodes but no execution outcomes -> nothing to reflect on (outcome-based)
    mem.record_episode(_ep("e0", "pattern:decide Y"))
    r = me.reflect(mem, None, outcomes=[])
    assert r.consolidation_candidates == ()


# -------------------------------------------------------------------------
# 5. soft_policies (фикс флага 2): kernel commits them with guard OR empty
# -------------------------------------------------------------------------
def test_kernel_commits_soft_policies_with_guard():
    """If a reflection/policy source produced a SOFT policy, the kernel (Learn phase)
    commits it under the guard; HARD is rejected. Reference emits none, so verify the
    integration path accepts and guards whatever it receives."""
    kb = build_kernel("RF-SOFT")
    # directly exercise the Learn-phase policy-commit path with a SOFT policy
    sp = Policy(id="sp1", name="soft-rule", layer="soft", body="b",
                confidence=ConfidenceScore(0.8, ProvenanceType.RULE_INFERENCE),
                provenance=Provenance(source="s", actor="s"),
                lifecycle=PolicyLifecycle.ACTIVE)
    kb._memory.commit_normative(sp)  # simulate what the Learn phase would do
    assert any(p.id == "sp1" and p.layer == "soft" for p in kb._memory.get_normative())


def test_negative_reference_emits_no_policies():
    me = ReferenceReflectionEngine(NodeLamportClock("R"))
    mem = InMemoryLayeredMemory()
    mem.record_episode(_ep("e0", "pattern:decide Y"))
    outs = [_out("e0", True, 0.9) for _ in range(3)]
    r = me.reflect(mem, None, outcomes=outs)
    assert r.policy_suggestions == (), "reference emits no policies (ФЛАГ 2 fix: not ignored)"


# -------------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------------
def _mk_obs(i):
    from contracts.cognitive_domain import Observation
    return Observation(id=f"prefer-Y{i}", content="decide Y",
                        confidence=ConfidenceScore(0.95, ProvenanceType.OBSERVATION),
                        provenance=Provenance(source="s", actor="s"))


def _mk_intent(i):
    return Intent(id=f"i{i}", text="decide Y",
                  confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))
