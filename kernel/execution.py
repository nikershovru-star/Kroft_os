"""Execution layer — LLM-FREE reference implementation (ТЗ-EX-01, ADR-063).

K1-compliant: stdlib + contracts only. Deterministic (I-09).

`ReferenceExecutionEnvironment` is a rule-based environment: it maps an Action's
payload to a deterministic ExecutionResult. This is the reference stand-in for a real
environment (a live agent/LLM/tool adapter plugs in later via IExecutor/IActionAdapter
without touching the kernel). It lets the system EXECUTE a decision and read a REAL
outcome (not the proxy), which is what makes Self-Evolving non-vacuous.

Rule map (deterministic, inspectable):
- payload contains "choose_blue" -> success=True,  reward=0.9, observation="blue_ok"
- payload contains "choose_red"   -> success=False, reward=0.1, observation="red_fail"
- anything else (unknown)         -> success=False, reward=0.0, observation="unknown"
"""

from __future__ import annotations

import time
from typing import Optional

from contracts.cognitive_domain import (
    Action,
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
)
from contracts.i_execution import (
    ExecutionResult,
    IActionAdapter,
    IExecutionEnvironment,
    IExecutor,
)


class ReferenceExecutionEnvironment(IExecutionEnvironment):
    """Deterministic rule-based environment. Maps Action payload -> ExecutionResult."""

    def __init__(self, clock: Optional[NodeLamportClock] = None) -> None:
        self._clock = clock if clock is not None else NodeLamportClock("exec-env")

    def step(self, action: Action) -> ExecutionResult:
        mark = self._clock.tick()
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        payload = (action.payload or "").lower()
        if "choose_blue" in payload:
            return ExecutionResult(
                action_id=action.id, success=True, observation="blue_ok",
                reward=0.9, confidence=conf, causal=mark)
        if "choose_red" in payload:
            return ExecutionResult(
                action_id=action.id, success=False, observation="red_fail",
                reward=0.1, confidence=conf, causal=mark)
        return ExecutionResult(
            action_id=action.id, success=False, observation="unknown_action",
            reward=0.0, confidence=conf, causal=mark)


class ReferenceExecutor(IExecutor):
    """Routes an Action to a reference environment (LLM-free core).

    Default backend is `ReferenceExecutionEnvironment`; an adapter for a specific
    `action.kind` may be supplied (IActionAdapter) to plug real backends later.
    `execute` is deterministic: no wall-clock sleep, `timeout` only guards a future
    async backend (ignored by the reference env, which is synchronous).
    """

    def __init__(self,
                 environment: Optional[IExecutionEnvironment] = None,
                 adapter: Optional[IActionAdapter] = None,
                 clock: Optional[NodeLamportClock] = None) -> None:
        self._env = environment if environment is not None else ReferenceExecutionEnvironment(clock)
        self._adapter = adapter
        self._clock = clock if clock is not None else NodeLamportClock("executor")

    def execute(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        _ = timeout  # reference env is synchronous & deterministic; no wall-clock wait
        if self._adapter is not None and self._adapter.kind == action.kind:
            return self._adapter.run(action, timeout)
        return self._env.step(action)
