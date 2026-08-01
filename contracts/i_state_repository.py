"""IStateRepository — обобщённый порт персистенции состояния ядра (ADR-029).

Введён в Phase B.3 как расширение идеи ISnapshotRepository: вместо узкого
SnapshotStore (только save/load dict) предусматривает ПОЛНУЮ модель
восстановления состояния, чтобы будущий Recovery Engine (Supervisor,
Checkpoint/Rollback, Cluster) не требовал второго рефакторинга.

Контракт (runtime_checkable Protocol):
  - save_state(dict)      — сохранить логическое состояние (runtime context, registry)
  - load_state() -> dict  — загрузить логическое состояние (или None)
  - save_snapshot(dict)   — атомарный snapshot (graph/index payload)
  - load_snapshot() -> dict
  - checkpoint(label)     — зафиксировать точку восстановления
  - rollback(label)       -> bool — откатиться к checkpoint

Реализация живёт в infrastructure (не в kernel). Kernel зависит ТОЛЬКО от
этого порта (K1 + ADR-028 Kernel Purity).
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class IStateRepository(Protocol):
    """Обобщённый порт персистенции состояния ядра."""

    def save_state(self, state: Dict[str, Any]) -> None:
        """Сохранить логическое состояние (runtime context, component registry)."""
        ...

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Загрузить логическое состояние. None если нет/бито."""
        ...

    def save_snapshot(self, payload: Dict[str, Any]) -> None:
        """Атомарный snapshot (composite graph/index payload)."""
        ...

    def load_snapshot(self) -> Optional[Dict[str, Any]]:
        """Загрузить snapshot. None если нет/бито."""
        ...

    def checkpoint(self, label: str) -> None:
        """Зафиксировать точку восстановления с меткой."""
        ...

    def rollback(self, label: str) -> bool:
        """Откатиться к checkpoint по метке. True если успешно."""
        ...
