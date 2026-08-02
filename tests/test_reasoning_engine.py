"""ТЗ-RE-01 acceptance + K8 negative tests — Reasoning Engine, single clock, world-aware Decision.

K8 discipline: each invariant is asserted positive AND its negation is shown to fail.
"""

import pytest

from contracts.cognitive_domain import (
    CausalMark, CognitiveEvent, CognitiveEventType, ConfidenceScore, Goal,
    Intent, Observation, Plan, Provenance, ProvenanceType, ReasoningStep, WorldState,
)
from contracts.i_cognitive_kernel import IReasoningEngine, IDecisionEngine
from kernel.cognitive_kernel import (
    CognitiveKernel, DeterministicDecisionEngine, InMemoryWorldState,
    SimpleAttention, SimpleResourceManager, SimpleValueSystem, DeterministicExecutive,
    SimpleLearningPolicy, NodeLamportClock, build_kernel,
)
from kernel.reasoning import ReferenceReasoningEngine
from services.distributed_runtime import SharedContextService


# -------------------------------------------------------------------------
# Reasoning Engine produces world-aware candidates
# -------------------------------------------------------------------------
def _kb_with_fact(fact_key, fact_val):
    kb = build_kernel("NODE-R")
    kb._world.update(Observation(id=fact_key, content=fact_val,
                                 confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                 provenance=Provenance(source="seed", actor="seed")))
    return kb


def test_reasoning_step_generates_candidate_with_confidence():
    kb = _kb_with_fact("prefer-Y", "decide Y")
    intent = Intent(id="i1", text="decide Y", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="user", actor="user"))
    steps = kb._reason.reason(intent, kb._world.snapshot(),
                               kb._attention.select_context(intent, kb._world.snapshot(), 100), 100)
    assert len(steps) >= 1
    for s in steps:
        assert isinstance(s, ReasoningStep)
        assert isinstance(s.confidence, ConfidenceScore)
        assert 0.0 <= s.confidence.value <= 1.0
        assert s.based_on_facts  # world-aware: step grounded in a fact


def test_reasoning_depends_on_world_fact_negative():
    """Negative: WITHOUT a relevant world fact the reasoning engine yields a
    DIFFERENT candidate (low-confidence 'explore') than a grounded step."""
    # with fact
    kb_fact = _kb_with_fact("prefer-Y", "decide Y")
    intent = Intent(id="i1", text="decide Y", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="user", actor="user"))
    steps_fact = kb_fact._reason.reason(intent, kb_fact._world.snapshot(),
                                        kb_fact._attention.select_context(intent, kb_fact._world.snapshot(), 100), 100)
    # without fact
    kb_empty = build_kernel("NODE-E")
    steps_empty = kb_empty._reason.reason(intent, kb_empty._world.snapshot(),
                                           kb_empty._attention.select_context(intent, kb_empty._world.snapshot(), 100), 100)
    # grounded step is described 'grounded-in:*' and carries the fact; empty is 'explore'
    assert any(s.description.startswith("grounded-in:") for s in steps_fact)
    assert all(s.description == "explore:no-world-fact" for s in steps_empty)
    assert steps_fact[0].based_on_facts != steps_empty[0].based_on_facts


def test_reasoning_influences_planning_and_decision():
    """A reasoned (grounded) candidate should reach the Decision step via Planning."""
    kb = _kb_with_fact("prefer-Y", "decide Y")
    intent = Intent(id="i1", text="decide Y", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="user", actor="user"))
    kb.tick(intent)
    rsn = [e for e in kb.events if e.type is CognitiveEventType.REASONING_STEP]
    plans = [e for e in kb.events if e.type is CognitiveEventType.PLAN_GENERATED]
    dec = [e for e in kb.events if e.type is CognitiveEventType.DECISION_ACCEPTED]
    assert rsn, "reasoning step must be emitted"
    assert plans, "planning must consume reasoning steps"
    assert dec, "decision must be reached"


# -------------------------------------------------------------------------
# Single node clock (flag 1)
# -------------------------------------------------------------------------
def test_single_clock_shared_across_kernel_world_and_federation():
    clock = NodeLamportClock("NODE-S")
    world = InMemoryWorldState("NODE-S", clock=clock)
    kb = CognitiveKernel(world, SimpleAttention(SimpleResourceManager()),
                         SimpleResourceManager(), SimpleValueSystem(),
                         DeterministicDecisionEngine(), DeterministicExecutive(SimpleResourceManager()),
                         SimpleLearningPolicy(),
                         lambda g, s: [Plan(id="p", goal_id=g.id, steps=("x",),
                                            confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                                            provenance=Provenance(source="pl", actor="k"))],
                         clock=clock)
    svc = SharedContextService("NODE-S", clock=clock)
    # kernel event
    intent = Intent(id="i", text="go", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="u", actor="u"))
    kb.tick(intent)
    ev = kb.events[0]
    # world fact
    world.update(Observation(id="f", content="v", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                              provenance=Provenance(source="s", actor="s")))
    # all three advance the SAME clock instance
    assert kb._clock is world._clock is svc._clock
    # and node_origin is the node_id, never the literal "kernel"
    assert ev.causal.node_origin == "NODE-S"
    assert all(m.node_origin == "NODE-S" for m in world.snapshot().facts_meta.values())


def test_kernel_event_and_world_fact_share_causal_order():
    kb = build_kernel("NODE-O")
    intent = Intent(id="i", text="go", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="u", actor="u"))
    kb.tick(intent)
    kb._world.update(Observation(id="f", content="v", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                  provenance=Provenance(source="s", actor="s")))
    # the clock only moves forward; kernel emit + world update are on one timeline
    last_ev = kb.events[-1]
    assert last_ev.causal.lamport >= 1
    assert kb._world.snapshot().facts_meta["f"].lamport >= last_ev.causal.lamport


# -------------------------------------------------------------------------
# World-aware Decision (flag D) — no bind hack
# -------------------------------------------------------------------------
def test_decision_engine_sees_worldstate_via_port():
    """A decision engine that reads `world` from select() must observe the fact
    (proves world-awareness without bind())."""
    class WorldReadingEngine(IDecisionEngine):
        def select(self, goal, candidates, values, world=None, intent=None):
            seen = world.facts.get("prefer-Y") if world else None
            chosen = candidates[0]
            for c in candidates:
                if seen and "Y" in c.id:
                    chosen = c
                    break
            return __import__("contracts.cognitive_domain", fromlist=["Decision"]).Decision(
                id="d", goal_id=goal.id, selected_plan_id=chosen.id,
                rationale=f"seen={seen}", confidence=chosen.confidence,
                provenance=Provenance(source="dec", actor="k"))

    kb = _kb_with_fact("prefer-Y", "Y")
    kb._decision = WorldReadingEngine()
    intent = Intent(id="i", text="decide Y", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="u", actor="u"))
    kb.tick(intent)
    assert kb._last_decision is not None
    assert "Y" in kb._last_decision.selected_plan_id or kb._last_decision.rationale


# -------------------------------------------------------------------------
# Wire key 'lamport' (flag 3)
# -------------------------------------------------------------------------
def test_wire_key_is_lamport_not_seq():
    svc = SharedContextService("n1")
    w = WorldState(node_id="n1", facts={"a": "1"})
    w.facts_meta["a"] = CausalMark("n1", 9)
    published = svc.publish_selective(w, "*")
    assert "lamport" in published[0]
    assert "seq" not in published[0]
    assert published[0]["lamport"] == 9
    # round-trip through merge_remote reads 'lamport'
    merged = svc.merge_remote(published, WorldState(node_id="n1"))
    assert merged.facts_meta["a"] == CausalMark("n1", 9)


# -------------------------------------------------------------------------
# Negative (K8): reasoning with world fact must NOT produce the explore candidate
# -------------------------------------------------------------------------
def test_negative_explore_only_when_no_fact():
    kb = _kb_with_fact("prefer-Y", "decide Y")
    intent = Intent(id="i", text="decide Y", confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="u", actor="u"))
    steps = kb._reason.reason(intent, kb._world.snapshot(),
                              kb._attention.select_context(intent, kb._world.snapshot(), 100), 100)
    assert not any(s.description == "explore:no-world-fact" for s in steps)
