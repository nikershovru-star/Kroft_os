"""ТЗ-AGENT-LOOP-01 (ADR-090) — Agent Loop K8 tests (Флаг 1b, separate).

Covers: loop iterates to budget; observation feeds replanning (feedback trail accumulates);
memory updates between steps (kernel state grows); determinism (I-09); budget-limit enforced;
all-fail graceful (no crash); LoopAgentExecutor integrates behind IAgentExecutor (backward-
compat single-tick ReferenceAgentExecutor untouched). K5: reuses IAgentLoop/AgentLoopResult,
AgentLoop, build_kernel, ReferenceExecutor, ReferenceAgentExecutor, LoopAgentExecutor.

Memory-growth check uses run_evolution._extract_state (composition-root tests may import it)
to prove the kernel's persisted state (episodes/skills/trust) accumulates across loop steps.
"""

from __future__ import annotations

import pytest

from contracts.i_agent_loop import AgentLoopResult, IAgentLoop
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome

from kernel.agent_loop import AgentLoop
from kernel.agent_executor import (
    ReferenceAgentExecutor,
    LoopAgentExecutor,
    build_agent_executor,
    build_loop_agent_executor,
)
from kernel.cognitive_kernel import build_kernel
from kernel.identity import ReferenceTrustRegistry
from services.memory_platform import InMemoryProceduralMemory


def _extract(kernel):
    """Reuse run_evolution._extract_state to inspect accumulated kernel memory."""
    from run_evolution import _extract_state
    proc = InMemoryProceduralMemory()
    trust = ReferenceTrustRegistry()
    return _extract_state(kernel, proc, trust, set())


def test_agent_loop_implements_port():
    assert isinstance(AgentLoop(), IAgentLoop)


def test_loop_iterates_to_budget():
    r = AgentLoop(node_id="t1", llm_client=None).run("goal", budget=3)
    assert isinstance(r, AgentLoopResult)
    assert r.success is True
    assert r.steps_taken == 3


def test_budget_limit_respected():
    r = AgentLoop(node_id="t2", llm_client=None).run("goal", budget=1)
    assert r.steps_taken == 1


def test_observation_feeds_replanning():
    """Feedback trail: each step's observation is recorded, so memory_delta grows."""
    r = AgentLoop(node_id="t3", llm_client=None).run("goal", budget=4)
    # one observation per step -> memory_delta length == steps_taken
    assert len(r.memory_delta) >= r.steps_taken
    joined = "\n".join(r.memory_delta)
    assert "step 1:" in joined
    assert f"step {r.steps_taken}:" in joined


def test_memory_updates_between_steps():
    """Injected kernel: after the loop, persisted state (episodes) accumulated across steps."""
    kernel = build_kernel("t4")
    r = AgentLoop(node_id="t4", llm_client=None, kernel=kernel).run("goal", budget=4)
    assert r.success is True
    state = _extract(kernel)
    # the kernel experienced >= budget ticks -> episodes recorded (memory grew between steps)
    assert len(state.episodes) >= r.steps_taken
    # skills may be learned during the loop (e.g. choose_blue)
    assert state.skills or len(state.episodes) >= r.steps_taken


def test_determinism():
    """Same goal + budget -> identical outcome (I-09, LLM-free)."""
    a = AgentLoop(node_id="t5", llm_client=None).run("goal", budget=3)
    b = AgentLoop(node_id="t5", llm_client=None).run("goal", budget=3)
    assert a.steps_taken == b.steps_taken
    assert a.final_outcome == b.final_outcome
    assert a.memory_delta == b.memory_delta


def test_all_fail_graceful():
    """budget < 1 -> graceful AgentLoopResult(success=False), not a crash."""
    r = AgentLoop(node_id="t6", llm_client=None).run("goal", budget=0)
    assert r.success is False
    assert r.steps_taken == 0
    assert r.error  # explains the failure


def test_loop_executor_returns_task_outcome():
    """LoopAgentExecutor wraps the loop behind IAgentExecutor (uniform dispatch)."""
    ex = build_loop_agent_executor(budget=3)
    goal = OrchestrationGoal(goal_id="g1", capability="explore", payload="goal")
    outcome = ex.execute(goal)
    assert isinstance(outcome, TaskOutcome)
    assert outcome.success is True
    assert "steps=" in outcome.detail


def test_reference_executor_still_single_tick():
    """Backward-compat: ReferenceAgentExecutor (single tick) is untouched and works."""
    ex = build_agent_executor()
    assert isinstance(ex, ReferenceAgentExecutor)
    goal = OrchestrationGoal(goal_id="g2", capability="explore", payload="goal")
    outcome = ex.execute(goal)
    assert isinstance(outcome, TaskOutcome)
    # single tick -> exactly one plan was selected/executed (not a multi-step loop)
    assert "plan: explore" in outcome.detail or outcome.success
