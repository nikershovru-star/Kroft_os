"""MultiAgentExecutor — route one Orchestrator agent-dispatch to the right per-capability agent.

K5/K6-compliant: services/ imports ONLY contracts.* + stdlib. This is a COMPOSITION-LEVEL
shim, NOT a new port or layer — it implements the existing IAgentExecutor (ADR-080) so the
Orchestrator (which accepts exactly one agent_executor) can drive MULTIPLE specialised agents
(research / architect / programmer / ...) without any change to kernel/orchestrator/contracts.

Why this exists: Orchestrator.dispatch(capability=X) already selects the best AGENT identity by
specialization x trust, but the single injected IAgentExecutor has no notion of which agent was
chosen. MultiAgentExecutor carries a capability->executor map and delegates; can_execute is True
only for capabilities it owns, so it composes cleanly with the orchestrator's agent path.
"""

from __future__ import annotations

from typing import Dict, List

from contracts.i_agent_executor import IAgentExecutor
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


class MultiAgentExecutor(IAgentExecutor):
    """Dispatch a goal to the registered per-capability agent executor."""

    def __init__(self, executors: List[IAgentExecutor]) -> None:
        # capability -> executor (last writer wins; normally one executor per capability)
        self._by_capability: Dict[str, IAgentExecutor] = {}
        for ex in executors:
            # each specialised executor declares its capability via can_execute; we probe by
            # constructing a minimal goal per known capability is overkill — instead executors
            # self-register by exposing a `capability` attribute when present.
            cap = getattr(ex, "capability", None)
            if cap is not None:
                self._by_capability[cap] = ex

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        ex = self._by_capability.get(goal.capability)
        if ex is None:
            return TaskOutcome(
                success=False, detail=f"no agent executor for capability={goal.capability}"
            )
        return ex.execute(goal)

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return goal.capability in self._by_capability
