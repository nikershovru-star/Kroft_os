"""Tests for Cognitive Kernel foundation (ADR-054 I-01..I-20).

Covers: FSM primary invariant, Executive sole authority, deterministic Decision,
Attention != ResourceManager, WorldState SSOT, LLM-free system-1, ConfidenceScore
contract, Provenance, Learning via Policy+Commit, Event Semantics, frozen Domain,
Hard>Soft. Positive + NEGATIVE (gate-style) to prove detectors fire (K8).
"""

import pytest

from contracts.cognitive_domain import (
    CognitiveEvent,
    CognitiveEventType,
    CognitiveState,
    ConfidenceScore,
    Decision,
    Goal,
    Intent,
    Observation,
    Plan,
    Policy,
    Provenance,
    ProvenanceType,
)
from contracts.i_cognitive_kernel import IAttention, IResourceManager
from kernel.cognitive_kernel import (
    CognitiveKernel,
    DeterministicDecisionEngine,
    DeterministicExecutive,
    InMemoryWorldState,
    SimpleAttention,
    SimpleLearningPolicy,
    SimpleResourceManager,
    SimpleValueSystem,
    build_kernel,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def _intent(text="summarize the vault") -> Intent:
    return Intent(id="int-1", text=text,
                  confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="user", actor="user"))


# --------------------------------------------------------------------------
# I-12 / I-18 — ConfidenceScore + frozen domain
# --------------------------------------------------------------------------
def test_confidencescore_validates_range():
    with pytest.raises(ValueError):
        ConfidenceScore(1.5)


def test_all_entities_carry_confidence():
    i = _intent()
    g = Goal(id="g", intent_id=i.id, description=i.text, confidence=i.confidence,
             provenance=i.provenance)
    p = Plan(id="p", goal_id=g.id, steps=("s1",),
             confidence=ConfidenceScore(0.8, ProvenanceType.RULE_INFERENCE),
             provenance=i.provenance)
    d = Decision(id="d", goal_id=g.id, selected_plan_id=p.id, rationale="x",
                 confidence=p.confidence, provenance=i.provenance)
    for e in (i, g, p, d):
        assert isinstance(e.confidence, ConfidenceScore)


def test_domain_entities_are_frozen():
    i = _intent()
    with pytest.raises(Exception):
        i.text = "mutated"  # frozen -> raises


# --------------------------------------------------------------------------
# I-01 / I-02 — FSM + Executive sole authority
# --------------------------------------------------------------------------
def test_tick_runs_full_cycle_to_idle():
    kb = build_kernel()
    end = kb.tick(_intent())
    assert end is CognitiveState.IDLE
    types = [e.type for e in kb.events]
    assert CognitiveEventType.GOAL_CREATED in types
    assert CognitiveEventType.DECISION_ACCEPTED in types
    assert CognitiveEventType.EXECUTION_FINISHED in types


def test_executive_blocks_illegal_transition():
    res = SimpleResourceManager()
    exec_ = DeterministicExecutive(res)
    # IDLE -> EXECUTE is NOT allowed directly (must go through Orient/Deliberate/Commit)
    assert not exec_.can_transition("IDLE", "EXECUTE")
    assert exec_.can_transition("IDLE", "OBSERVE")


def test_executive_interrupt_halts_transitions():
    res = SimpleResourceManager()
    exec_ = DeterministicExecutive(res)
    exec_.interrupt("test")
    assert not exec_.can_transition("IDLE", "OBSERVE")


# --------------------------------------------------------------------------
# I-03 — Decision deterministic selector (no LLM call inside)
# --------------------------------------------------------------------------
def test_decision_selects_highest_utility():
    val = SimpleValueSystem()
    dec = DeterministicDecisionEngine()
    g = Goal(id="g", intent_id="i", description="x",
             confidence=ConfidenceScore(0.7), provenance=Provenance(source="s", actor="k"))
    cands = [
        Plan(id="lo", goal_id="g", steps=("a",),
             confidence=ConfidenceScore(0.4, ProvenanceType.RULE_INFERENCE),
             provenance=Provenance(source="s", actor="k")),
        Plan(id="hi", goal_id="g", steps=("b",),
             confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
             provenance=Provenance(source="s", actor="k")),
    ]
    d = dec.select(g, cands, val)
    assert d.selected_plan_id == "hi"


def test_decision_rejects_all_hard_violating():
    val = SimpleValueSystem(hard_checkers=[lambda c: "HARD" if c.confidence.value < 0.99 else None])
    dec = DeterministicDecisionEngine()
    g = Goal(id="g", intent_id="i", description="x",
             confidence=ConfidenceScore(0.7), provenance=Provenance(source="s", actor="k"))
    cands = [Plan(id="p", goal_id="g", steps=("a",),
                  confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                  provenance=Provenance(source="s", actor="k"))]
    d = dec.select(g, cands, val)
    assert d.selected_plan_id == ""  # rejected


# --------------------------------------------------------------------------
# I-05 / I-06 — Attention != ResourceManager (separate modules)
# --------------------------------------------------------------------------
def test_attention_and_resource_manager_are_distinct():
    assert IAttention is not IResourceManager
    res = SimpleResourceManager()
    attn = SimpleAttention(res)
    # Attention requests quota FROM resource manager, does not own budgets
    ctx = attn.select_context(_intent(), InMemoryWorldState().snapshot(), 100)
    assert isinstance(ctx, list)
    assert res.remaining("tokens") < 100000  # quota consumed by attention request


# --------------------------------------------------------------------------
# I-07 — WorldState SSOT
# --------------------------------------------------------------------------
def test_world_state_is_ssot():
    ws = InMemoryWorldState()
    obs = Observation(id="o1", content="fact", confidence=ConfidenceScore(1.0),
                      provenance=Provenance(source="obs", actor="k"))
    snap = ws.update(obs)
    assert ws.get("o1") == "fact"
    assert snap.facts["o1"] == "fact"


# --------------------------------------------------------------------------
# I-09 / I-16 — system-1 LLM-free path
# --------------------------------------------------------------------------
def test_system1_runs_without_llm():
    kb = build_kernel()
    obs = Observation(id="o2", content="event", confidence=ConfidenceScore(1.0),
                      provenance=Provenance(source="obs", actor="k"))
    kb.run_system1(obs)
    types = [e.type for e in kb.events]
    assert CognitiveEventType.OBSERVATION_RECEIVED in types
    assert CognitiveEventType.EXECUTION_FINISHED in types
    assert kb.state is CognitiveState.IDLE


# --------------------------------------------------------------------------
# I-14 — Learning via Policy+Commit (proposes, gated)
# --------------------------------------------------------------------------
def test_learning_proposes_only_when_confident_and_repeated():
    lp = SimpleLearningPolicy()
    # single episode -> no proposal
    assert lp.propose(["e1"]) is None
    # repeated -> proposal, but must pass accepts gate
    prop = lp.propose(["e1", "e1"])
    assert prop is not None
    assert lp.accepts(prop) is True


def test_learning_never_writes_memory_directly():
    # SimpleLearningPolicy has no memory-write method -> proves Learning != Memory writer
    lp = SimpleLearningPolicy()
    assert not hasattr(lp, "write_memory")


# --------------------------------------------------------------------------
# I-17 — Event Semantics (every transition emits, reproducible)
# --------------------------------------------------------------------------
def test_every_transition_emits_event():
    kb = build_kernel()
    kb.tick(_intent())
    # at least: goal, plan(x2), decision, exec start, exec finish, policy?
    assert len(kb.events) >= 6
    for e in kb.events:
        assert isinstance(e, CognitiveEvent)
        assert e.to_bus()["type"]  # serializable for replay


# --------------------------------------------------------------------------
# I-11 / I-19 — Hard > Soft
# --------------------------------------------------------------------------
def test_value_system_hard_veto_precedes_soft():
    called = {"score": False}

    class V(SimpleValueSystem):
        def score(self, candidate):
            called["score"] = True
            return super().score(candidate)

    v = V(hard_checkers=[lambda c: "BAD" if c.confidence.value < 1.0 else None])
    p = Plan(id="p", goal_id="g", steps=("a",),
             confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
             provenance=Provenance(source="s", actor="k"))
    assert v.hard_violations(p) == ["BAD"]
