"""IDelegationService — делегирование подзадач агентам (Phase C, Wave C1, ADR-103).

K5/K6-compliant: contracts + stdlib only. Отдельный port от IOrchestrator:
- IOrchestrator (ADR-073) маршрутизирует goal -> executor по trust; единый шаг.
- IDelegationService ведёт DAG родитель->ребёнок ДЛЯ многошаговой координации и
  препятствует delegation-циклам (A->B->A) и превышению глубины (аудит #3).

Delegation-DAG: каждый delegation = edge parent_goal_id -> child_goal_id. Перед
назначением исполнителя проверяем:
  (a) cycle: child не должен (транзитивно) делегировать обратно предку;
  (b) max_depth: глубина от корня не превышает лимит.
Speaker selection = capability-index O(1) через переданный MultiAgentExecutor.can_execute
(не O(n) перебор всех агентов).

Frozen entities, NO timestamp.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


@dataclass(frozen=True)
class DelegationDecision:
    """Результат delegation: кому делегировать + статус проверок DAG."""

    child_goal_id: str
    capability: str
    executor_id: str          # выбранный исполнитель (capability-index)
    depth: int                # глубина в DAG от корня
    accepted: bool            # False если cycle / max_depth нарушены
    reason: str               # почему accepted / отклонено


class DelegationError(Exception):
    """Base delegation error."""


class DelegationCycle(DelegationError):
    """Обнаружен delegation-цикл (A->B->A)."""


class DelegationTooDeep(DelegationError):
    """Превышена max_depth."""


class IDelegationService(ABC):
    """Назначает исполнителя подзадачи по capability-индексу + охраняет DAG от циклов/глубины."""

    @abstractmethod
    def delegate(
        self,
        parent_goal_id: str,
        child_goal: OrchestrationGoal,
        executor_resolver,
    ) -> DelegationDecision:
        """Назначить исполнителя child_goal.

        executor_resolver: callable(capability: str) -> Optional[executor_id]
        (capability-index lookup, НЕ перебор). Возвращает DelegationDecision.
        При cycle / max_depth -> accepted=False (НЕ raise, чтобы caller мог залогировать
        и понизить trust, как в Orchestrator.dispatch)."""
        raise NotImplementedError

    @abstractmethod
    def record_outcome(self, child_goal_id: str, outcome: TaskOutcome) -> None:
        """Зафиксировать исход делегирования (для trust evolution у caller-а)."""
        raise NotImplementedError

    @abstractmethod
    def is_ancestor(self, ancestor_goal_id: str, goal_id: str) -> bool:
        """Транзитивная проверка: является ли ancestor предком goal_id (для cycle detection)."""
        raise NotImplementedError

    @abstractmethod
    def depth_of(self, goal_id: str) -> int:
        """Глубина goal_id в DAG (корень = 0)."""
        raise NotImplementedError
