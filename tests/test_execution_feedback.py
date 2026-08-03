"""K8 tests for ТЗ-EX-01 Execution layer + real outcome-feedback.

Covers:
- execute returns a REAL ExecutionResult (not a proxy)
- a FAILED action yields success=False EVEN THOUGH the decision was accepted
  (the key negative: the proxy would have said True)
- real outcome replaces the proxy when an executor is wired
- repeated REAL failures drive RF-01 deprecation (evolution from genuine failure)
- negative: no executor -> proxy fallback; unknown action -> success=False
- separation: ExecutionResult (raw) != ExecutionOutcome (Reflection signal)
- O1 / K1 / K6 / K8
"""

from __future__ import annotations

from contracts.cognitive_domain import (
    Action,
    ConfidenceScore,
    ExecutionOutcome,
    Intent,
    NodeLamportClock,
    Plan,
    Provenance,
    ProvenanceType,
)
from contracts.i_execution import ExecutionResult
from contracts.i_planner import IPlanner
from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor, ReferenceExecutionEnvironment
from kernel.reflection import ReferenceReflectionEngine
from kernel.memory_evolution import ReferenceMemoryEvolution


def _cs(v: float = 0.9) -> ConfidenceScore:
    return ConfidenceScore(v, ProvenanceType.RULE_INFERENCE)


def _intent() -> Intent:
    return Intent(id="i1", text="do something",
                  confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))


class _RedPlanner(IPlanner):
    """Deterministic planner that always proposes a choose_red plan."""
    def plan(self, goal, steps, world, budget, intent=None):
        return [Plan(id="p-red", goal_id=goal.id, steps=("choose_red",),
                     confidence=_cs(), provenance=Provenance(source="t", actor="t"))]


class _BluePlanner(IPlanner):
    """Deterministic planner that always proposes a choose_blue plan."""
    def plan(self, goal, steps, world, budget, intent=None):
        return [Plan(id="p-blue", goal_id=goal.id, steps=("choose_blue",),
                     confidence=_cs(), provenance=Provenance(source="t", actor="t"))]


# ---------------------------------------------------------------------------
# 1. execute returns a REAL ExecutionResult
# ---------------------------------------------------------------------------
def test_executor_returns_real_execution_result():
    ex = ReferenceExecutor()
    act = Action(id="a1", kind="execute_plan", payload="choose_blue",
                 confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    res = ex.execute(act)
    assert isinstance(res, ExecutionResult)
    assert res.success is True
    assert res.reward == 0.9
    assert res.observation == "blue_ok"


# ---------------------------------------------------------------------------
# 2. FAILED action -> success=False even though decision ACCEPTED (vs proxy)
# ---------------------------------------------------------------------------
def test_failed_action_yields_false_despite_accepted_decision():
    k = build_kernel("EX-R")
    k._planner = _RedPlanner()
    k.attach_executor(ReferenceExecutor())
    # decision IS accepted (plan chosen), but the executed action fails in env
    k.tick(_intent())
    outcome = k._outcomes[-1]
    # proxy would report success=True (decision accepted); real env reports False
    assert outcome.success is False, "real environment failure must override proxy"
    assert outcome.utility == 0.1


def test_environment_rule_map_is_deterministic():
    env = ReferenceExecutionEnvironment()
    blue = Action(id="b", kind="execute_plan", payload="x choose_blue y",
                  confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    red = Action(id="r", kind="execute_plan", payload="choose_red",
                 confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    unk = Action(id="u", kind="execute_plan", payload="do thing",
                 confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    assert env.step(blue).success is True and env.step(blue).reward == 0.9
    assert env.step(red).success is False and env.step(red).reward == 0.1
    assert env.step(unk).success is False and env.step(unk).reward == 0.0


# ---------------------------------------------------------------------------
# 3. real outcome replaces proxy when executor wired
# ---------------------------------------------------------------------------
def test_real_outcome_replaces_proxy_when_executor_present():
    k = build_kernel("EX-P")
    k._planner = _RedPlanner()
    # no executor yet -> proxy reports success (decision accepted)
    k.tick(_intent())
    assert k._outcomes[-1].success is True
    # now wire real executor -> real failure reported
    k.attach_executor(ReferenceExecutor())
    k.tick(_intent())
    assert k._outcomes[-1].success is False


# ---------------------------------------------------------------------------
# 4. repeated REAL failures -> RF-01 deprecation (evolution from genuine failure)
# ---------------------------------------------------------------------------
def test_repeated_real_failures_drive_rf01_deprecation():
    # build real outcomes from real ExecutionResults (choose_red repeatedly fails)
    ex = ReferenceExecutor()
    me = ReferenceMemoryEvolution(NodeLamportClock("R"))
    # seed memory with a repeated experience pattern
    for i in range(3):
        me._memory.record_episode(_ep(f"e{i}", "pattern:decide X")) if hasattr(me, "_memory") else None
    # build 3 real outcomes via the executor on a red plan
    red_act = Action(id="a", kind="execute_plan", payload="choose_red",
                     confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    real_outcomes = [
        ExecutionOutcome(episode_id=f"e{i}", success=ex.execute(red_act).success,
                        utility=ex.execute(red_act).reward, confidence=_cs(),
                        causal=NodeLamportClock("o").tick())
        for i in range(3)
    ]
    refl = ReferenceReflectionEngine(NodeLamportClock("R"))
    # memory with the repeated pattern so deprecation has a target
    from kernel.memory_store import InMemoryLayeredMemory
    mem = InMemoryLayeredMemory()
    for i in range(3):
        mem.record_episode(_ep(f"e{i}", "pattern:decide X"))
    report = refl.reflect(mem, None, outcomes=real_outcomes)
    assert report.deprecation_candidates == ("pattern:decide X",), \
        "genuine repeated failures must drive deprecation (non-vacuous evolution)"


def _ep(eid: str, summary: str):
    return __import__("contracts.cognitive_domain", fromlist=["Episode"]).Episode(
        id=eid, summary=summary, confidence=_cs(),
        provenance=Provenance(source="t", actor="t"))


# ---------------------------------------------------------------------------
# 5. negative: no executor -> proxy fallback; unknown action -> success=False
# ---------------------------------------------------------------------------
def test_no_executor_proxy_fallback_keeps_decision_success():
    k = build_kernel("EX-F")
    k._planner = _RedPlanner()  # would fail in real env, but no executor wired
    k.tick(_intent())
    assert k._outcomes[-1].success is True, "without executor, proxy fallback holds"


def test_unknown_action_is_failure():
    ex = ReferenceExecutor()
    act = Action(id="x", kind="execute_plan", payload="totally unknown",
                 confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    res = ex.execute(act)
    assert res.success is False
    assert res.reward == 0.0


# ---------------------------------------------------------------------------
# 6. separation Result (raw) vs Outcome (Reflection signal)
# ---------------------------------------------------------------------------
def test_result_and_outcome_are_distinct_concepts():
    ex = ReferenceExecutor()
    act = Action(id="a", kind="execute_plan", payload="choose_blue",
                 confidence=_cs(), provenance=Provenance(source="t", actor="t"))
    res = ex.execute(act)
    assert isinstance(res, ExecutionResult)
    # Outcome is CONSTRUCTED from the result, not the same object
    out = ExecutionOutcome(episode_id=act.id, success=res.success,
                           utility=res.reward, confidence=res.confidence,
                           causal=res.causal)
    assert not isinstance(out, ExecutionResult)
    assert out.success == res.success and out.utility == res.reward


# ---------------------------------------------------------------------------
# 7. O1: execution does not mutate HARD/FSM/contracts (negative surface check)
# ---------------------------------------------------------------------------
def test_executor_has_no_hard_mutation_surface():
    # the reference executor only returns ExecutionResult; it never touches
    # FSM state, kernel structure, or contracts. Assert it exposes no such API.
    ex = ReferenceExecutor()
    assert not hasattr(ex, "commit_normative")
    assert not hasattr(ex, "deprecate_hard")
    assert not hasattr(ex, "mutate_contract")
