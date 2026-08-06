"""AgentRuntime — тонкий facade мультиагентного рантайма (Phase C, Wave C1, ADR-103).

K6 (аудит #7): импортирует ИСКЛЮЧИТЕЛЬНО контракты-порты. Конкретные executors /
blackboard / delegation инжектит composition root (ADR-103 §5). Facade НЕ содержит
координационных if-веток (аудит #1: не god-object) — делегирует IDelegationService.

Hard rule (аудит #9): агенты НЕ вызывают друг друга напрямую. Обмен контекстом — через
IBlackboard (delegate_step пишет результат шага в team-scope, следующий шаг читает snapshot).
"""

from __future__ import annotations

import hashlib
from typing import List, Optional, Tuple

from contracts.i_agent_runtime import IAgentRuntime, WorkflowResult
from contracts.i_blackboard import IBlackboard
from contracts.i_delegation import IDelegationService
from contracts.i_agent_executor import IAgentExecutor
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_identity import ITrustRegistry
from contracts.i_telemetry import ITelemetrySink
from contracts.i_approval_gate import ApprovalRequest, IApprovalGate


class AgentRuntime(IAgentRuntime):
    """Facade: единая точка входа; композиция (blackboard/delegation/executors) — извне.

    Wave C3: опц. trust_registry + telemetry — delegation trust-delta и telemetry-события.
    Wave C6: опц. approval_gate + sensitive_capabilities — человеческий предохранитель.
    Без них поведение НЕИЗМЕННО (backward-compat): guard-ами по None / пустому списку.
    """

    def __init__(
        self,
        executor: IAgentExecutor,
        blackboard: IBlackboard,
        delegation: IDelegationService,
        root_capability: str = "research",
        trust_registry: Optional[ITrustRegistry] = None,
        telemetry: Optional[ITelemetrySink] = None,
        approval_gate: Optional[IApprovalGate] = None,
        sensitive_capabilities: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self._executor = executor
        self._blackboard = blackboard
        self._delegation = delegation
        self._root_capability = root_capability
        self._trust = trust_registry
        self._telemetry = telemetry
        self._approval = approval_gate
        self._sensitive = set(sensitive_capabilities or ())

    def run_workflow(self, goal: str, root_goal_id: Optional[str] = None) -> WorkflowResult:
        # I-09: стабильная деривация (HE hash() — рандомизован per-process via PYTHONHASHSEED).
        rid = root_goal_id or f"root:{hashlib.sha256(goal.encode('utf-8')).hexdigest()[:12]}"
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
            # Флаг 2 (light): executor_id = capability (capability-index, приемлемо для C1,
            # т.к. capability уникален на executor). Когда появится неоднозначность
            # (2 executor на 1 capability), вернуть реальный id исполнителя из registry.
            probe = OrchestrationGoal(goal_id=f"probe:{cap}", capability=cap)
            if self._executor.can_execute(probe):
                return cap
            return None

        decision = self._delegation.delegate(parent_goal_id, child_goal, resolver)
        if not decision.accepted:
            return TaskOutcome(success=False, detail=decision.reason)
        # Wave C6: человеческий предохранитель для чувствительных capabilities (default OFF)
        if self._approval is not None and child_goal.capability in self._sensitive:
            adec = self._approval.request_approval(
                ApprovalRequest(
                    action_id=child_goal.goal_id,
                    capability=child_goal.capability,
                    payload=str(child_goal.payload),
                    agent_id=decision.executor_id,
                )
            )
            if not adec.approved:
                return TaskOutcome(
                    success=False,
                    detail=f"approval denied: {adec.reason}",
                )
        # исполняем через MultiAgentExecutor (capability->executor map)
        outcome = self._executor.execute(child_goal)
        self._delegation.record_outcome(child_goal.goal_id, outcome)
        # Wave C3: trust-delta (SOFT) + telemetry — только если инжектнуты (backward-compat)
        if self._trust is not None:
            # executor_id = capability (Флаг 2 C1: capability-index); при неоднозначности
            # вернуть реальный id исполнителя из registry.
            self._trust.record_outcome(decision.executor_id, outcome.success)
        if self._telemetry is not None:
            self._telemetry.record(
                "agent_runtime.delegation",
                1.0 if outcome.success else 0.0,
                tags={"capability": child_goal.capability, "executor": decision.executor_id},
            )
        # stigmergy: пишем результат шага в team-scope blackboard (НЕ прямой вызов)
        self._blackboard.append(
            scope=f"team.{child_goal.goal_id}",
            writer_id=decision.executor_id,
            payload=outcome.detail,
        )
        return outcome
