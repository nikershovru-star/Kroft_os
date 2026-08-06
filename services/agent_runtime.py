"""AgentRuntime — тонкий facade мультиагентного рантайма (Phase C, Wave C1, ADR-103).

K6 (аудит #7): импортирует ИСКЛЮЧИТЕЛЬНО контракты-порты. Конкретные executors /
blackboard / delegation инжектит composition root (ADR-103 §5). Facade НЕ содержит
координационных if-веток (аудит #1: не god-object) — делегирует IDelegationService.

Hard rule (аудит #9): агенты НЕ вызывают друг друга напрямую. Обмен контекстом — через
IBlackboard (delegate_step пишет результат шага в team-scope, следующий шаг читает snapshot).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from contracts.i_agent_runtime import IAgentRuntime, WorkflowResult
from contracts.i_blackboard import IBlackboard
from contracts.i_delegation import IDelegationService
from contracts.i_agent_executor import IAgentExecutor
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


class AgentRuntime(IAgentRuntime):
    """Facade: единая точка входа; композиция (blackboard/delegation/executors) — извне."""

    def __init__(
        self,
        executor: IAgentExecutor,
        blackboard: IBlackboard,
        delegation: IDelegationService,
        root_capability: str = "research",
    ) -> None:
        self._executor = executor
        self._blackboard = blackboard
        self._delegation = delegation
        self._root_capability = root_capability

    def run_workflow(self, goal: str, root_goal_id: Optional[str] = None) -> WorkflowResult:
        rid = root_goal_id or f"root:{abs(hash(goal)) % 10_000}"
        root_goal = OrchestrationGoal(goal_id=rid, capability=self._root_capability, payload=goal)
        outcome = self.delegate_step(rid, root_goal)
        return WorkflowResult(
            root_goal_id=rid,
            success=outcome.success,
            outcomes=(outcome,),
            detail=outcome.detail,
        )

    def delegate_step(self, parent_goal_id: str, child_goal: OrchestrationGoal) -> TaskOutcome:
        # capability-index через публичный can_execute порта (O(1) lookup в MultiAgentExecutor)
        def resolver(cap: str) -> Optional[str]:
            probe = OrchestrationGoal(goal_id=f"probe:{cap}", capability=cap)
            if self._executor.can_execute(probe):
                return cap
            return None

        decision = self._delegation.delegate(parent_goal_id, child_goal, resolver)
        if not decision.accepted:
            return TaskOutcome(success=False, detail=decision.reason)
        # исполняем через MultiAgentExecutor (capability->executor map)
        outcome = self._executor.execute(child_goal)
        self._delegation.record_outcome(child_goal.goal_id, outcome)
        # stigmergy: пишем результат шага в team-scope blackboard (НЕ прямой вызов)
        self._blackboard.append(
            scope=f"team.{child_goal.goal_id}",
            writer_id=decision.executor_id,
            payload=outcome.detail,
        )
        return outcome
