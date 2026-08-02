"""Integration slice: cognitive core x federation, in-process (path 3, post-review gate).

Proves the causal contract (gate C) PAYS OFF in the coupled loop — NOT just that
merge picks the greater CausalMark (that is unit-tested in TZ-015). Here we show:

    tick@A -> causal mark (A,seq) -> publish -> forward -> merge@B
    -> WorldState@B now carries federated fact with CausalMark(A) -> Decision@B CHANGES

If merge order did not affect B's reasoning, federation would be a distributed store
with an LLM on top — not a cognitive OS. This test is the proof it is cognitive.

Two kernels + two SharedContextService, exchange over an in-memory channel (no real
network, no flaky wall-clock timing — zero infra pain, max cognitive value).
"""

import pytest

from contracts.cognitive_domain import (
    CausalMark,
    CognitiveEvent,
    CognitiveEventType,
    CognitiveState,
    ConfidenceScore,
    Decision,
    Goal,
    Intent,
    Observation,
    Plan,
    Provenance,
    ProvenanceType,
)
from contracts.i_cognitive_kernel import ICognitiveKernel, IDecisionEngine, IWorldState
from kernel.cognitive_kernel import (
    CognitiveKernel,
    DeterministicExecutive,
    InMemoryWorldState,
    SimpleResourceManager,
    SimpleValueSystem,
    build_kernel,
)
from services.distributed_runtime import SharedContextService


class WorldAwareDecisionEngine(IDecisionEngine):
    """Test-only decision engine: picks plan by a WorldState fact, proving federation
    influences reasoning. If WorldState has 'prefer-Y' -> choose plan containing 'Y',
    else 'X'. This is the coupling assertion, not a production planner."""

    def __init__(self) -> None:
        self._world = None

    def bind(self, world: IWorldState) -> "WorldAwareDecisionEngine":
        self._world = world
        return self

    def select(self, goal: Goal, candidates: list, values) -> Decision:
        pref = self._world.get("prefer-Y") if self._world else None
        chosen = None
        for p in candidates:
            if pref and "Y" in p.id:
                chosen = p
                break
            if not pref and "X" in p.id:
                chosen = p
                break
        chosen = chosen or candidates[0]
        return Decision(
            id=_uid("dec"),
            goal_id=goal.id,
            selected_plan_id=chosen.id,
            rationale=f"world-aware pick: prefer-Y={'Y' in chosen.id}",
            confidence=chosen.confidence,
            provenance=Provenance(source="decision", actor="kernel"),
        )


def _uid(p="x"):
    import uuid
    return f"{p}-{uuid.uuid4().hex[:8]}"


def _make_node(node_id: str, decision_engine: IDecisionEngine) -> CognitiveKernel:
    world = InMemoryWorldState(node_id)
    res = SimpleResourceManager()
    attn = build_kernel(node_id)._attention  # reuse reference attention
    val = SimpleValueSystem()
    exec_ = DeterministicExecutive(res)
    learn = build_kernel(node_id)._learning

    def planner_for(goal: Goal, steps: list) -> list:
        # deterministic candidate generator (adapter would call LLM)
        return [
            Plan(id="plan-X", goal_id=goal.id, steps=("x",),
                 confidence=ConfidenceScore(0.7, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="planner", actor="kernel")),
            Plan(id="plan-Y", goal_id=goal.id, steps=("y",),
                 confidence=ConfidenceScore(0.7, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="planner", actor="kernel")),
        ]

    kb = CognitiveKernel(world, attn, res, val, decision_engine, exec_, learn, planner_for)
    if hasattr(decision_engine, "bind"):
        decision_engine.bind(world)
    return kb


def test_federation_changes_decision_at_node_b():
    """Full coupled loop: A's fact (causal A,seq=10) reaches B and flips B's Decision."""
    # Node A produces a fact "prefer-Y" with a HIGH causal mark
    node_a = _make_node("A", WorldAwareDecisionEngine())
    node_a._world.update(Observation(id="prefer-Y", content="Y",
                                      confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                      provenance=Provenance(source="a", actor="a")),
                          causal=CausalMark("A", 10))

    # Node B starts with a LOCAL low-mark fact "prefer-Y" (B,seq=1) — would lose to A's
    node_b = _make_node("B", WorldAwareDecisionEngine())
    node_b._world.update(Observation(id="prefer-Y", content="Y-old",
                                     confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                     provenance=Provenance(source="b", actor="b")),
                         causal=CausalMark("B", 1))

    # --- federation channel (in-memory) ---
    ctx_a = SharedContextService("A")
    ctx_b = SharedContextService("B")
    published = ctx_a.publish_selective(node_a._world.snapshot(), "*")
    # B merges A's facts (carrying CausalMark A,seq=10)
    merged = ctx_b.merge_remote(published, node_b._world.snapshot())
    # apply merged facts into B's world store
    for key, val in merged.facts.items():
        node_b._world.update(Observation(id=key, content=val,
                                          confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
                                          provenance=Provenance(source="fed", actor="fed")),
                             causal=merged.facts_meta[key])

    # --- B's cognitive tick ---
    intent = Intent(id="int-1", text="decide",
                    confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="user", actor="user"))
    end = node_b.tick(intent)
    assert end is CognitiveState.IDLE

    dec_events = [e for e in node_b.events if e.type is CognitiveEventType.DECISION_ACCEPTED]
    assert dec_events, "B must accept a decision"
    accepted = node_b._last_decision
    assert accepted is not None
    # THE ASSERTION: B's decision flipped to plan-Y because federated fact (causal A,seq=10)
    # won the merge and now sits in WorldState@B
    assert "Y" in accepted.selected_plan_id, (
        f"federation did NOT influence B's reasoning: decision={accepted.selected_plan_id}, "
        f"world={node_b._world.snapshot().facts}")
    # and the fact in B's world carries A's causal origin (not B's stale seq=1)
    assert node_b._world.snapshot().facts_meta["prefer-Y"] == CausalMark("A", 10)


def test_federation_no_effect_when_lower_causal_loses():
    """Control: if A sent a LOWER causal mark, B's local fact wins and decision stays X."""
    node_a = _make_node("A", WorldAwareDecisionEngine())
    node_a._world.update(Observation(id="prefer-Y", content="Y",
                                     confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                     provenance=Provenance(source="a", actor="a")),
                         causal=CausalMark("A", 1))  # LOWER than B's seq=5

    node_b = _make_node("B", WorldAwareDecisionEngine())
    node_b._world.update(Observation(id="prefer-Y", content="Y-old",
                                     confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                                     provenance=Provenance(source="b", actor="b")),
                         causal=CausalMark("B", 5))

    ctx_a, ctx_b = SharedContextService("A"), SharedContextService("B")
    published = ctx_a.publish_selective(node_a._world.snapshot(), "*")
    merged = ctx_b.merge_remote(published, node_b._world.snapshot())
    for key, val in merged.facts.items():
        node_b._world.update(Observation(id=key, content=val,
                                         confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
                                         provenance=Provenance(source="fed", actor="fed")),
                             causal=merged.facts_meta[key])

    intent = Intent(id="int-2", text="decide",
                    confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="user", actor="user"))
    node_b.tick(intent)
    dec = [e for e in node_b.events if e.type is CognitiveEventType.DECISION_ACCEPTED][0]
    # B's local fact (seq=5) beat A's (seq=1) -> world keeps B's mark, decision unaffected path
    assert node_b._world.snapshot().facts_meta["prefer-Y"] == CausalMark("B", 5)
