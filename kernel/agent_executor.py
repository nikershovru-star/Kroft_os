"""Reference agent executor (ТЗ-AGENT-EXEC-01, ADR-080) — real agent tick -> TaskOutcome.

ReferenceAgentExecutor implements IAgentExecutor: given an OrchestrationGoal it translates
the goal into an Intent, runs a REAL cognitive tick (build_kernel: perceive->reason->plan->
decide->execute), and returns the ACTUAL TaskOutcome derived from that tick — NOT a delegated
success=True. This closes Флаг 2 FED-EXEC-01 / Флаг 2 SKILL-EVOLVE-01: the orchestrator's
agent path now yields a real outcome from which trust evolves (success +, failure -).

K1/K6: depends ONLY on contracts (i_agent_executor, i_orchestrator, cognitive_domain) +
stdlib. The kernel + executor live in kernel/ (their own layer), so this module is lawfully
in kernel/ and does NOT import adapters/services. Build (Флаг C) is standalone — НЕ in the
god-factory build_kernel.

O1: the executor never mutates HARD/FSM; it only produces an outcome. Trust is evolved by the
CALLER (orchestrator) via ITrustRegistry.record_outcome — SOFT, uniform with plugins/remote/skill.
I-09: by default the tick is LLM-free (no llm_client passed to build_kernel) -> deterministic,
reproducible outcome. A live model is OPTIONAL (pass llm_client for advisory only; the kernel
still makes the final decision).

Failure handling: on ANY exception the executor returns TaskOutcome(success=False, detail=...)
rather than raising or reporting success — so the orchestrator's trust loop evolves correctly
(failure LOWERS trust, exactly as a real failed run would).
"""

from __future__ import annotations

from typing import Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Provenance,
    ProvenanceType,
)
from contracts.i_agent_executor import IAgentExecutor
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor


class ReferenceAgentExecutor(IAgentExecutor):
    """Run one goal as a real autonomous agent tick; return the computed TaskOutcome."""

    def __init__(self, default_agent_id: str = "agent", llm_client=None) -> None:
        self._default_agent_id = default_agent_id
        self._llm_client = llm_client

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        # The agent identity for this goal: prefer an explicit chosen id carried in the goal
        # payload, else the default executor agent. We key the kernel node by goal.goal_id so
        # each execution is an isolated, deterministic tick (no cross-goal state leakage).
        node_id = f"{self._default_agent_id}:{goal.goal_id}"
        try:
            kernel = build_kernel(node_id, llm_client=self._llm_client)
            kernel.attach_executor(ReferenceExecutor())

            intent = Intent(
                id=goal.goal_id,
                text=str(goal.payload if goal.payload is not None else goal.capability),
                confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="orchestrator", actor="orchestrator"),
            )
            kernel.tick(intent)
            plan = kernel._last_selected_plan
            success = plan is not None
            detail = (
                "agent tick produced plan: " + "|".join(plan.steps)
                if success
                else "agent tick: no plan selected/executed"
            )
            return TaskOutcome(success=success, detail=detail)
        except Exception as exc:  # noqa: BLE001 — executor faults must lower trust, not crash
            return TaskOutcome(success=False, detail=f"agent tick failed: {type(exc).__name__}: {exc}")

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        # OrchestrationGoal is always translatable to an Intent; default executable.
        return True


def build_agent_executor(
    default_agent_id: str = "agent", llm_client=None
) -> ReferenceAgentExecutor:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return ReferenceAgentExecutor(default_agent_id=default_agent_id, llm_client=llm_client)


class LoopAgentExecutor(IAgentExecutor):
    """Multi-step agent executor (ТЗ-AGENT-LOOP-01) — drives an AgentLoop to a goal.

    Wraps the iterative AgentLoop (kernel/agent_loop.py) behind the IAgentExecutor port
    so the orchestrator's uniform TaskOutcome dispatch accepts it unchanged (backward-
    compat: ReferenceAgentExecutor remains the single-tick path). On any loop failure it
    returns TaskOutcome(success=False) so trust evolves correctly (failure LOWERS trust).
    """

    def __init__(self, default_agent_id: str = "agent-loop", llm_client=None,
                 budget: int = 5, knowledge_index=None, memory=None,
                 embedding=None) -> None:
        self._default_agent_id = default_agent_id
        self._llm_client = llm_client
        self._budget = budget
        self._knowledge_index = knowledge_index
        self._memory = memory  # ТЗ-L10: shared layered memory (persisted by run_kroft)
        self._embedding = embedding  # ТЗ-L10.4: reuse existing EmbeddingAdapter for semantic episodic retrieval
        self.capability = "loop"  # lawful routing key (ТЗ-L8: dedicated capability)

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        node_id = f"{self._default_agent_id}:{goal.goal_id}"
        goal_text = str(goal.payload if goal.payload is not None else goal.capability)
        try:
            from kernel.agent_loop import AgentLoop
            loop = AgentLoop(node_id=node_id, llm_client=self._llm_client,
                             knowledge_index=self._knowledge_index,
                             memory=self._memory,
                             embedding=self._embedding)
            result = loop.run(goal_text, budget=self._budget)
            return TaskOutcome(
                success=result.success,
                detail=(result.final_outcome or result.error)
                + f" [steps={result.steps_taken}]",
            )
        except Exception as exc:  # noqa: BLE001 — executor faults must lower trust, not crash
            return TaskOutcome(success=False,
                               detail=f"agent loop failed: {type(exc).__name__}: {exc}")

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return True


def build_loop_agent_executor(
    default_agent_id: str = "agent-loop", llm_client=None, budget: int = 5
) -> LoopAgentExecutor:
    """Standalone factory (Флаг C) — multi-step agent executor over AgentLoop."""
    return LoopAgentExecutor(default_agent_id=default_agent_id,
                             llm_client=llm_client, budget=budget)
