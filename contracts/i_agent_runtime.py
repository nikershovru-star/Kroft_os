"""IAgentRuntime — тонкий facade мультиагентного рантайма (Phase C, Wave C1, ADR-103).

K5/K6-compliant: contracts + stdlib only. Это ТОЛЬКО точка входа; оркестрационная
логика живёт в IDelegationService / IBlackboard / координаторах. Facade делегирует,
не содержит координационных if-веток (аудит #1: не god-object).

Конкретная композиция (какие executors, какой blackboard) инжектится из composition root
(ADR-103 §5 K6) — facade зависит только от портов.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


@dataclass(frozen=True)
class WorkflowResult:
    """Результат сквозного прогона задачи через рантайм (frozen, reproducible)."""

    root_goal_id: str
    success: bool
    outcomes: Tuple[TaskOutcome, ...]
    detail: str = ""


class IAgentRuntime(ABC):
    """Единая точка входа мультиагентного выполнения задачи."""

    @abstractmethod
    def run_workflow(self, goal: str, root_goal_id: Optional[str] = None) -> WorkflowResult:
        """Прогнать задачу через рантайм (делегирование + blackboard-обмен)."""
        raise NotImplementedError

    @abstractmethod
    def delegate_step(self, parent_goal_id: str, child_goal: OrchestrationGoal) -> TaskOutcome:
        """Делегировать один шаг (через IDelegationService + MultiAgentExecutor)."""
        raise NotImplementedError
