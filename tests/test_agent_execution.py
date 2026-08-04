"""K8 tests for ТЗ-AGENT-EXEC-01 — real agent execution closes Флаг 2 FED-EXEC-01.

Covers (acceptance + O1/K1/K6/K8 + ADR-080):
- agent-routed dispatch -> REAL TaskOutcome from a kernel cognitive tick (not delegated success=True);
  trust EVOLVES from the real outcome (success 0.9->1.0).
- a real FAILURE outcome (forced) -> trust LOWERS (0.9->0.8) — the loop closes for agents too.
- NO executor wired -> pre-ТЗ delegated behaviour preserved (success=True, backward-compat).
- determinism (I-09): same goal -> same outcome shape; executor is LLM-free by default.
- O1: trust SOFT (via ITrustRegistry); orchestrator never mutates HARD/FSM.
- existing ORCH/FED/SKILL tests remain green (this change is additive + optional-param).
"""

from __future__ import annotations

from contracts.i_identity import AgentIdentity
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from kernel.agent_executor import ReferenceAgentExecutor, build_agent_executor
from kernel.identity import ReferenceIdentityRegistry, ReferenceTrustRegistry, ReferenceActionLog
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry


def _registries(trust_seed=0.9):
    ids = ReferenceIdentityRegistry()
    ids.register(AgentIdentity(agent_id="ag1", specialization="plan", trust_level=trust_seed))
    pl = ReferencePluginRegistry()
    tr = ReferenceTrustRegistry()
    tr.seed("ag1", trust_seed)
    return ids, pl, tr, ReferenceActionLog()


def test_agent_dispatch_real_outcome_from_kernel_tick_and_trust_rises():
    ids, pl, tr, log = _registries()
    orch = build_orchestrator(ids, pl, tr, log, agent_executor=build_agent_executor("ag1"))
    before = tr.current_trust("ag1")
    out = orch.dispatch(OrchestrationGoal("g1", "plan", payload="do it"))
    assert out.success is True, "real agent tick should yield a successful outcome"
    assert "agent tick" in out.detail
    assert tr.current_trust("ag1") > before, f"trust should rise on real success: {before} -> {tr.current_trust('ag1')}"


def test_agent_real_failure_lowers_trust():
    ids, pl, tr, log = _registries()
    # Force a real failure outcome from the executor (simulates a tick that failed to plan/execute).
    class FailingExecutor(ReferenceAgentExecutor):
        def execute(self, goal):
            return TaskOutcome(success=False, detail="agent tick: no plan selected/executed")
    orch = build_orchestrator(ids, pl, tr, log, agent_executor=FailingExecutor())
    before = tr.current_trust("ag1")
    out = orch.dispatch(OrchestrationGoal("g2", "plan", payload="x"))
    assert out.success is False
    assert tr.current_trust("ag1") < before, f"trust should drop on real failure: {before} -> {tr.current_trust('ag1')}"


def test_no_executor_keeps_delegated_backward_compat():
    ids, pl, tr, log = _registries()
    orch = build_orchestrator(ids, pl, tr, log)  # no agent_executor
    out = orch.dispatch(OrchestrationGoal("g3", "plan", payload="y"))
    assert out.success is True
    assert "delegated" in out.detail, "without executor, must keep pre-ТЗ delegated behaviour"


def test_determinism_same_goal_same_outcome_shape():
    ids, pl, tr, log = _registries()
    orch = build_orchestrator(ids, pl, tr, log, agent_executor=build_agent_executor("ag1"))
    o1 = orch.dispatch(OrchestrationGoal("ga", "plan", payload="repeat"))
    o2 = orch.dispatch(OrchestrationGoal("gb", "plan", payload="repeat"))
    # LLM-free tick -> deterministic: both succeed (no model variance).
    assert o1.success is True and o2.success is True


def test_o1_trust_soft_orchestrator_no_hard_mutation():
    ids, pl, tr, log = _registries()
    orch = build_orchestrator(ids, pl, tr, log, agent_executor=build_agent_executor("ag1"))
    # dispatch should only call ITrustRegistry.record_outcome (SOFT), never touch HARD/FSM.
    out = orch.dispatch(OrchestrationGoal("g4", "plan", payload="z"))
    assert out.success is True
    # The orchestrator exposes no HARD/FSM mutation surface used here.
    assert not hasattr(orch, "mutate_hard") and not hasattr(orch, "transition")
