"""IAgentExecutor — Agent execution port (ТЗ-AGENT-EXEC-01, ADR-080).

K1-compliant: stdlib + contracts only. One-port-per-boundary: this is the port for
EXECUTING ONE goal through a real autonomous agent tick, returning a normalized
``TaskOutcome``. It is DELIBERATELY DISTINCT from ``IAgentPlatform`` (contracts/
i_agent_platform.py, ADR-014), which returns a rich, traceable ``AgentResult`` for a
free-form string ``goal`` and coordinates Planner+Memory+Knowledge+Tools+Workflow+
Policies+LLM+Evaluator as a platform. Here the unit is an ``OrchestrationGoal`` (the
same VO the orchestrator routes) and the output is the SAME ``TaskOutcome`` the
orchestrator already uses for plugins/remote/skill — so trust evolution (record_outcome)
stays uniform across all executor kinds (ORCH-01 closure).

Why a new port and not reuse IAgentPlatform:
- Different boundary: goal-shape (OrchestrationGoal vs str) + result-shape
  (TaskOutcome vs AgentResult). Forcing IAgentPlatform into the orchestrator's
  TaskOutcome flow would either break one-port-per-boundary or require a lossy
  mapping of AgentResult -> TaskOutcome at every call site.
- The orchestrator's dispatch loop is uniform over TaskOutcome; the executor port
  MUST speak TaskOutcome. IAgentPlatform remains the higher-level "run a whole agent
  mission" boundary (ADR-014), untouched.

O1: the executor never mutates HARD/FSM; it only produces an outcome. Trust is evolved
by the CALLER (orchestrator) via ITrustRegistry.record_outcome — SOFT, as everywhere.
Determinism (I-09): a reference executor runs an LLM-free cognitive tick by default, so
the outcome is reproducible without a live model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


class IAgentExecutor(ABC):
    """Port: execute one ``OrchestrationGoal`` as a real agent tick -> ``TaskOutcome``.

    A reference implementation (ReferenceAgentExecutor, kernel/agent_executor.py)
    translates the goal into an Intent, runs a cognitive tick (build_kernel), and
    returns the REAL outcome derived from the tick (a plan was selected + executed).
    On any failure it returns ``TaskOutcome(success=False)`` — it does NOT silently
    report success (this is precisely the Флаг 2 FED-EXEC behaviour being closed).
    """

    @abstractmethod
    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        """Run the goal as a real agent tick; return the computed TaskOutcome.

        Must raise NOTHING for normal executor faults — return TaskOutcome(success=False,
        detail=...) so the orchestrator's trust loop evolves correctly (failure LOWERS trust).
        """
        raise NotImplementedError

    # Optional capability probe (default: always executable). Lets the orchestrator skip
    # an executor that cannot handle a capability without paying for a full tick.
    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return True
