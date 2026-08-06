"""IWorkflowCoordinator — сборка Workflow из goal + выбор стратегии (Phase C, Wave C2, ADR-103).

K5/K6-compliant: contracts + stdlib only. Переиспользует сущности Workflow/Step (ADR-013),
НЕ дублирует WorkflowExecutor (тот для LLM-router workflow, другой boundary). Исполнение
steps идёт через IAgentRuntime.delegate_step (уже готовый рантайм C1).

build_workflow(goal) -> Workflow (deterministic: id от sha256(goal), НЕ hash()).
choose_strategy() -> ICoordinationStrategy (инжектится из composition root; C2 = Stigmergy).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from contracts.i_coordination_strategy import ICoordinationStrategy
from contracts.i_workflow import Workflow


class IWorkflowCoordinator(ABC):
    """Строит Workflow из goal и выбирает координационную стратегию."""

    @abstractmethod
    def build_workflow(self, goal: str) -> Workflow:
        """Детерминированная сборка Workflow из goal (id=sha256(goal)[:12], I-09)."""
        raise NotImplementedError

    @abstractmethod
    def choose_strategy(self) -> ICoordinationStrategy:
        """Выбрать координационную стратегию (C2: Stigmergy; слоты Sequential/Hierarchical)."""
        raise NotImplementedError

    @abstractmethod
    def run(self, workflow: Workflow) -> Workflow:
        """Исполнить workflow через IAgentRuntime.delegate_step (stigmergy blackboard-обмен).

        Возвращает НОВЫЙ Workflow (copy-on-write, ADR-013) с обновлёнными step-статусами.
        """
        raise NotImplementedError
