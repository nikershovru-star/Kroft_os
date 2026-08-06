"""IBlackboard — координационное состояние задачи (Phase C, Wave C1, ADR-103).

K5/K6-compliant: contracts + stdlib only. ОТДЕЛЬНЫЙ port от ILayeredMemory (ADR-103 §4.3):
- IBlackboard = координационное состояние, нужное ДРУГИМ агентам для координации
  (промежуточные результаты шагов, статусы, handoff-сигналы). Versioned, single-writer
  per scope, TTL.
- ILayeredMemory = память агента (долгосрочная семантика, эпизоды, навыки).
Граница охраняется arch-gate (ADR-103 §4.3 criteria): в blackboard пишется ТОЛЬКО
координационное; личный контекст агента -> ILayeredMemory.

Frozen entities, NO timestamp (ADR-013 reproducibility): версия — логический монотонный
ординал (не wall-clock), так два прогона одного input равны.

Single-writer per scope: запись несёт writer_id; конкурентная запись тем же scope другим
writer-ом отклоняется (raise BlackboardContention) — устраняет lost updates без блокировок.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class BlackboardEntry:
    """Одна иммутабельная запись blackboard (append-only)."""

    version: int
    scope: str
    writer_id: str
    payload: Any
    seq: int  # монотонный ord внутри scope (для детерминизма)


@dataclass(frozen=True)
class BlackboardSnapshot:
    """Read-only снимок scope на момент version."""

    scope: str
    version: int
    entries: Tuple[BlackboardEntry, ...]


class BlackboardError(Exception):
    """Base blackboard error."""


class BlackboardContention(BlackboardError):
    """Конкурентная запись тем же scope другим writer-ом (single-writer violation)."""


class BlackboardScopeUnknown(BlackboardError):
    """Snapshot запрошен для несуществующего scope."""


class IBlackboard(ABC):
    """Координационное состояние задачи: versioned, single-writer per scope, snapshot-read."""

    @abstractmethod
    def append(self, scope: str, writer_id: str, payload: Any) -> BlackboardEntry:
        """Добавить запись. Монотонный version. Если scope уже пишется ДРУГИМ writer-ом
        (single-writer violation между snapshot и append) -> BlackboardContention.
        Возвращает созданную BlackboardEntry (с version/seq)."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self, scope: str) -> BlackboardSnapshot:
        """Read-only снимок scope (все entries на текущую version). Один writer не меняется."""
        raise NotImplementedError

    @abstractmethod
    def latest_version(self, scope: str) -> int:
        """Текущий version scope (0 если пуст)."""
        raise NotImplementedError

    @abstractmethod
    def scopes(self) -> Tuple[str, ...]:
        """Все известные scope."""
        raise NotImplementedError
