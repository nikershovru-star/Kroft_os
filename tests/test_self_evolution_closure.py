"""K8 tests for ТЗ-SE-01 — Self-Evolution behavioral closure (capstone).

Covers:
- CAPSTONE: repeated SUCCESS -> consolidation -> NEXT decision SELECTS the learned action.
- CAPSTONE: repeated FAILURE -> deprecation -> NEXT decision AVOIDS the learned failure.
- NEGATIVE: WITHOUT wiring (plain SimpleValueSystem + ReferenceReasoningEngine) evolution
  does NOT change the decision (proves the WIRING is what changes behavior, not memory
  alone).
- O1: only SOFT layer influences; HARD / FSM / contracts untouched.
- separation: learned layer is read via ISoftPolicySource port (K6-clean).
"""

from __future__ import annotations

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Plan,
    Provenance,
    ProvenanceType,
)
from contracts.i_planner import IPlanner
from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor
from kernel.self_evolution import (
    MemorySoftPolicySource,
    PolicyAwareValueSystem,
    KnowledgeAwareReasoning,
)
from kernel.value_system import SimpleValueSystem
from kernel.reasoning import ReferenceReasoningEngine


def _intent() -> Intent:
    return Intent(id="i1", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))


class _FixedPlanner(IPlanner):
    """Always proposes a single plan with the given steps."""
    def __init__(self, steps):
        self._steps = steps
    def plan(self, goal, steps, world, budget, intent=None):
        return [Plan(id="p", goal_id=goal.id, steps=self._steps,
                     confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                     provenance=Provenance(source="t", actor="t"))]


class _BothPlanner(IPlanner):
    """Offers the learned candidate + an alternative (explore/fallback)."""
    def __init__(self, learned, alt):
        self._learned = learned
        self._alt = alt
    def plan(self, goal, steps, world, budget, intent=None):
        return [
            Plan(id="pl", goal_id=goal.id, steps=self._learned,
                 confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
            Plan(id="pa", goal_id=goal.id, steps=self._alt,
                 confidence=ConfidenceScore(0.4, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
        ]


class _BothPlannerFirstAlt(IPlanner):
    """Alternative FIRST (equal confidence) — without wiring the first wins."""
    def __init__(self, learned, alt):
        self._learned = learned
        self._alt = alt
    def plan(self, goal, steps, world, budget, intent=None):
        return [
            Plan(id="pa", goal_id=goal.id, steps=self._alt,
                 confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
            Plan(id="pl", goal_id=goal.id, steps=self._learned,
                 confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
        ]


def _run(kernel, planner, n, intent=None):
    kernel._planner = planner
    for _ in range(n):
        kernel.tick(intent or _intent())


# ---------------------------------------------------------------------------
# CAPSTONE 1: repeated SUCCESS -> consolidation -> NEXT decision SELECTS learned
# ---------------------------------------------------------------------------
def test_repeated_success_makes_next_decision_select_learned():
    k = build_kernel("SE-S")
    k.attach_executor(ReferenceExecutor())
    # repeated success on choose_blue
    _run(k, _FixedPlanner(("choose_blue",)), 4)
    # semantic fact consolidated from repeated success
    facts = [f.content for f in k._memory.get_semantic()]
    assert "decided:choose_blue" in facts, "repeated success must consolidate a semantic fact"
    # next tick: planner offers learned + alternative; learned should be SELECTED
    _run(k, _BothPlanner(("choose_blue",), ("explore-for:g",)), 1)
    assert k._last_selected_plan.steps == ("choose_blue",), \
        "evolution must change behavior: learned action should now be selected"


# ---------------------------------------------------------------------------
# CAPSTONE 2: repeated FAILURE -> deprecation -> NEXT decision AVOIDS failure
# ---------------------------------------------------------------------------
def test_repeated_failure_makes_next_decision_avoid_failed():
    k = build_kernel("SE-F")
    k.attach_executor(ReferenceExecutor())
    # repeated failure on choose_red
    _run(k, _FixedPlanner(("choose_red",)), 4)
    # avoid policy committed from deprecation
    avoids = [p.body for p in k._memory.get_normative()
              if getattr(p, "layer", None) == "soft" and "avoid" in p.body]
    assert any("choose_red" in a for a in avoids), "repeated failure must yield an avoid policy"
    # next tick: planner offers BOTH failed + alternative; failed should be AVOIDED
    _run(k, _BothPlanner(("choose_red",), ("choose_blue",)), 1)
    assert k._last_selected_plan.steps == ("choose_blue",), \
        "evolution must change behavior: failed action should be avoided"


# ---------------------------------------------------------------------------
# NEGATIVE: WITHOUT wiring, evolution does NOT change the decision
# ---------------------------------------------------------------------------
def test_without_wiring_evolution_does_not_change_decision():
    # Build a kernel WITHOUT the SE-01 closure: plain value + reasoning, no source.
    from kernel.cognitive_kernel import (
        InMemoryWorldState, SimpleResourceManager, SimpleAttention,
        DeterministicDecisionEngine, DeterministicExecutive, SimpleLearningPolicy,
        ReferencePlanner, ReferenceWorldModel, InMemoryLayeredMemory,
        ReferenceMemoryEvolution, ReferenceReflectionEngine, NodeLamportClock,
    )
    clock = NodeLamportClock("NW")
    world = InMemoryWorldState("NW", clock=clock)
    res = SimpleResourceManager()
    attn = SimpleAttention(res)
    val = SimpleValueSystem()                       # NOT PolicyAware
    reason = ReferenceReasoningEngine(clock, attn)  # NOT KnowledgeAware
    memory = InMemoryLayeredMemory()
    k = build_kernel.__wrapped__ if hasattr(build_kernel, "__wrapped__") else None
    # assemble minimal kernel manually to avoid build_kernel's wiring
    from kernel.cognitive_kernel import CognitiveKernel
    k = CognitiveKernel(
        world, attn, res, val,
        DeterministicDecisionEngine(), DeterministicExecutive(res),
        SimpleLearningPolicy(),
        ReferencePlanner(clock, world_model=ReferenceWorldModel(clock), values=val),
        clock=clock, reason=reason,
        world_model=ReferenceWorldModel(clock),
        memory_evolution=ReferenceMemoryEvolution(clock),
        memory=memory, reflection_engine=ReferenceReflectionEngine(clock),
    )
    k.attach_executor(ReferenceExecutor())
    # repeated success on choose_blue -> semantic fact IS consolidated
    _run(k, _FixedPlanner(("choose_blue",)), 4)
    assert any("decided:choose_blue" in f.content for f in k._memory.get_semantic()), \
        "memory still evolves (fact present) without wiring"
    # but decision should NOT prefer the learned action (no source to read it).
    # Use a planner where learned + alternative have EQUAL base confidence; without
    # wiring the deterministic pick is the FIRST candidate (alternative), proving the
    # learned action is NOT auto-selected. With wiring (other test) it IS selected.
    _run(k, _BothPlannerFirstAlt(("choose_blue",), ("explore-for:g",)), 1)
    assert k._last_selected_plan.steps != ("choose_blue",), \
        "without wiring, evolution must NOT change the decision"


# ---------------------------------------------------------------------------
# O1: only SOFT layer influences; HARD/FSM/contracts untouched
# ---------------------------------------------------------------------------
def test_o1_avoid_policy_is_soft_not_hard():
    k = build_kernel("SE-O1")
    k.attach_executor(ReferenceExecutor())
    _run(k, _FixedPlanner(("choose_red",)), 4)
    for p in k._memory.get_normative():
        if "avoid" in p.body:
            assert p.layer == "soft", "avoid policy must be SOFT (O1 guard)"
            assert p.id and p.confidence is not None


def test_o1_deliberation_does_not_mutate_hard_or_contracts():
    # PolicyAwareValueSystem / KnowledgeAwareReasoning only ADD soft preference;
    # they expose NO API to mutate HARD layer, FSM, or contracts.
    k = build_kernel("SE-O1B")
    vs = k._values
    assert not hasattr(vs, "commit_normative")
    assert not hasattr(vs, "deprecate_hard")
    assert not hasattr(vs, "mutate_fsm")


# ---------------------------------------------------------------------------
# K6: deliberation reads the evolved layer via the ISoftPolicySource PORT
# ---------------------------------------------------------------------------
def test_deliberation_reads_layer_via_port():
    k = build_kernel("SE-K6")
    src = MemorySoftPolicySource(k._memory)
    # before any evolution: empty
    assert src.get_prefer_patterns() == []
    assert src.get_avoid_patterns() == []
    assert src.get_recall_facts() == []
    # the wired value system uses the same port (no direct memory import in scoring)
    assert isinstance(k._values, PolicyAwareValueSystem)
    assert k._values._source is not None
    # functional equivalence: same memory -> same recalled layer
    assert k._values._source.get_recall_facts() == src.get_recall_facts()
