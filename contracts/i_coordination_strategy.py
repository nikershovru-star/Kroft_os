"""ICoordinationStrategy — стратегия координации агентов (Phase C, Wave C1, ADR-103).

K5/K6-compliant: contracts + stdlib only. Strategy-объект (аудит #8 Open/Closed):
новый паттерн координации = новый strategy-класс, правки runtime НЕТ.

Wave C1: реализуется ТОЛЬКО StigmergyStrategy (базовый паттерн). SequentialStrategy /
HierarchicalStrategy — СЛОТЫ в интерфейсе, НЕ реализуются, пока не появится реальный
сценарий, требующий их (адский #3).

Stigmergy: агенты пишут промежуточные результаты в IBlackboard и читают snapshot,
НЕ вызывая друг друга напрямую (аудит #9: hard rule event-driven).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Tuple

from contracts.i_blackboard import BlackboardSnapshot


@dataclass(frozen=True)
class CoordinationStep:
    """Один шаг координации: какой scope читать/писать и через какой capability."""

    scope: str
    writer_capability: str
    reader_capability: str


class ICoordinationStrategy(ABC):
    """Стратегия координации: как агенты обмениваются контекстом задачи."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя стратегии: 'stigmergy' | 'sequential' (slot) | 'hierarchical' (slot)."""
        raise NotImplementedError

    @abstractmethod
    def next_step(self, prior: Tuple[CoordinationStep, ...], snapshot: BlackboardSnapshot) -> CoordinationStep:
        """Следующий шаг координации на основе истории шагов + snapshot blackboard."""
        raise NotImplementedError
