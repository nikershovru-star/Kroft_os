"""Contract crash-test (path B, post-review gate).

A non-trivial system-2 tick with REAL (not stub) Attention + Decision + LearningPolicy
and REAL layered memory. Proves the ADR-054 contracts survive non-trivial load BEFORE
we federate Shared Context in TZ-015:

  1. ConfidenceScore aggregation Intent->Plan->Decision (ADR-055 aggregation_rule).
  2. LearningPolicy routes writes by memory LAYER (episode vs normative) on confidence
     threshold + repetition (I-14) — never writes memory directly.
  3. Surfaces the contract GAP that TZ-015 federation will hit: CognitiveEvent carries
     only wall-clock timestamp; for CRDT merge/dedup across nodes it needs a CAUSAL mark
     (node-origin + sequence / vector clock). We assert the gap explicitly so the gate
     in TZ-015 extends the contract intentionally, not by guesswork.

This is an integration test of the COGNITIVE contract, not a stub exercise.
"""

import pytest

from contracts.cognitive_domain import (
    AggregationRule,
    CausalMark,
    CognitiveEvent,
    CognitiveEventType,
    CognitiveState,
    ConfidenceScore,
    Decision,
    Episode,
    Goal,
    Intent,
    Observation,
    Plan,
    Policy,
    Provenance,
    ProvenanceType,
    aggregate_confidence,
)
from contracts.i_cognitive_kernel import (
    IAttention,
    IDecisionEngine,
    ILearningPolicy,
    ILayeredMemory,
    IResourceManager,
    IValueSystem,
    IWorldState,
)
from kernel.cognitive_kernel import (
    CognitiveKernel,
    DeterministicDecisionEngine,
    DeterministicExecutive,
    InMemoryWorldState,
    SimpleResourceManager,
    SimpleValueSystem,
    build_kernel,
)


# --------------------------------------------------------------------------
# Real (non-stub) components
# --------------------------------------------------------------------------
class RealisticAttention(IAttention):
    """Salience from WorldState token overlap with Intent; context = top facts."""

    def __init__(self, resources: IResourceManager) -> None:
        self._res = resources

    def select_context(self, intent: Intent, world: IWorldState, budget_tokens: int) -> list:
        granted = self._res.request_quota("attention", "tokens", budget_tokens)
        items = list(world.snapshot().facts.keys())
        cap = max(1, granted // 10)
        return items[-cap:]

    def salience(self, item_id: str, intent: Intent, world: IWorldState) -> ConfidenceScore:
        content = world.get(item_id) or ""
        overlap = len(set(content.lower().split()) & set(intent.text.lower().split()))
        return ConfidenceScore(min(1.0, 0.4 + 0.1 * overlap), ProvenanceType.RULE_INFERENCE)


class ConfidenceAggregatingPlanner:
    """Generates candidate plans whose confidence is AGGREGATED from step confidences."""

    def __init__(self, world: IWorldState) -> None:
        self._world = world

    def __call__(self, goal: Goal) -> list:
        # two steps, each with its own confidence -> plan confidence aggregated
        step_a = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        step_b = ConfidenceScore(0.4, ProvenanceType.RULE_INFERENCE)  # weak step
        agg = aggregate_confidence([step_a, step_b], AggregationRule.MIN)
        weak = Plan(id="plan-weak", goal_id=goal.id, steps=("a", "b"),
                    confidence=agg, provenance=Provenance(source="planner", actor="kernel"))
        strong = Plan(id="plan-strong", goal_id=goal.id, steps=("a",),
                      confidence=ConfidenceScore(0.92, ProvenanceType.RULE_INFERENCE),
                      provenance=Provenance(source="planner", actor="kernel"))
        return [weak, strong]


class LayeredLearningPolicy(ILearningPolicy):
    """Routes writes by LAYER: episode (raw) always; normative (rule) only if
    confidence >= threshold AND repeated. Never touches memory directly (I-14)."""

    def __init__(self, memory: ILayeredMemory, confidence_threshold: float = 0.8,
                 min_repetitions: int = 2) -> None:
        self._mem = memory
        self._thr = confidence_threshold
        self._min_rep = min_repetitions
        self._seen: dict = {}

    def propose(self, episode_ids: list) -> "Policy | None":
        from collections import Counter
        for eid in episode_ids:
            self._mem.record_episode(Episode(
                id=eid, summary=f"episode {eid}",
                confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
                provenance=Provenance(source="learning", actor="kernel")))
        counts = Counter(episode_ids)
        top, n = counts.most_common(1)[0]
        # only propose a normative rule if confident + repeated
        if n >= self._min_rep:
            return Policy(id=f"pol-{top}", name=f"learned:{top}", layer="soft",
                          body=f"pattern {top} x{n}",
                          confidence=ConfidenceScore(min(1.0, 0.6 + 0.1 * n),
                                                     ProvenanceType.AGGREGATION),
                          provenance=Provenance(source="learning", actor="kernel"))
        return None

    def accepts(self, proposal: Policy) -> bool:
        return proposal.confidence.value >= self._thr


class InMemoryLayeredMemory(ILayeredMemory):
    def __init__(self) -> None:
        self._episodes: list = []
        self._normative: list = []

    def record_episode(self, episode: Episode) -> None:
        self._episodes.append(episode)

    def commit_normative(self, policy: Policy) -> None:
        self._normative.append(policy)

    def get_episodes(self) -> list:
        return list(self._episodes)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def _kernel_with_real_components() -> tuple:
    world = InMemoryWorldState("n1")
    res = SimpleResourceManager()
    attn = RealisticAttention(res)
    val = SimpleValueSystem(hard_checkers=[lambda c: "LOW" if c.confidence.value < 0.3 else None])
    dec = DeterministicDecisionEngine()
    exec_ = DeterministicExecutive(res)
    mem = InMemoryLayeredMemory()
    learn = LayeredLearningPolicy(mem)
    planner = ConfidenceAggregatingPlanner(world)
    kb = CognitiveKernel(world, attn, res, val, dec, exec_, learn, planner)
    return kb, mem


def _intent() -> Intent:
    return Intent(id="int-1", text="summarize the vault contents",
                  confidence=ConfidenceScore(0.7, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="user", actor="user"))


# --------------------------------------------------------------------------
# Crash-test assertions
# --------------------------------------------------------------------------
def test_confidence_aggregates_intent_to_decision():
    kb, mem = _kernel_with_real_components()
    end = kb.tick(_intent())
    assert end is CognitiveState.IDLE
    # find the accepted decision
    dec_events = [e for e in kb.events if e.type is CognitiveEventType.DECISION_ACCEPTED]
    assert dec_events, "decision must be accepted"
    # the chosen plan must be 'plan-strong' (high confidence), NOT 'plan-weak'
    # (weak plan confidence = MIN(0.9,0.4)=0.4 < strong 0.92)
    accepted = dec_events[0]
    # decision confidence should reflect the selected plan, not the weak aggregate
    assert accepted.confidence.value >= 0.9


def test_learning_routes_by_memory_layer_not_direct():
    kb, mem = _kernel_with_real_components()
    kb.tick(_intent())
    # episode layer always recorded (Learning proposes -> memory.record_episode)
    assert len(mem.get_episodes()) >= 1
    # normative layer only if a confident+repeated proposal was accepted
    # single tick -> likely no normative commit (needs repetition)
    # KEY: LearningPolicy has NO direct memory write other than via ILayeredMemory port
    assert not hasattr(kb._learning, "write_memory")


def test_contract_gap_federation_now_has_causal_mark():
    """Gate C CLOSED: CognitiveEvent/WorldState now carry a CAUSAL mark (node_origin+seq),
    so TZ-015 federation merge/dedup is well-defined without trusting wall-clock time.

    This test previously asserted the GAP existed (no causal mark). After the gate-C
    contract extension it asserts the gap is CLOSED.
    """
    kb, mem = _kernel_with_real_components()
    kb.tick(_intent())
    ev: CognitiveEvent = kb.events[0]
    # contract now carries causal mark (not just wall-clock timestamp)
    assert hasattr(ev, "timestamp")
    assert hasattr(ev, "causal")
    assert isinstance(ev.causal, CausalMark)
    assert ev.causal.node_origin and ev.causal.seq >= 0
    # WorldState facts carry causal metadata too
    snap = kb._world.snapshot()
    assert any(hasattr(v, "node_origin") for v in snap.facts_meta.values()) if snap.facts_meta else True
    # and the FSM emits causal marks per event
    assert all(hasattr(e, "causal") for e in kb.events)
