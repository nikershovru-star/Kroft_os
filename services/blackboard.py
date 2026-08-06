"""InMemoryBlackboard — versioned, single-writer-per-scope blackboard (Phase C, Wave C1).

K1/K6: services импортирует только contracts + stdlib. НЕ импортирует ILayeredMemory
(ADR-103 §4.3 boundary). Это координационное состояние задачи, НЕ память агента.

Single-writer per scope: scope блокируется за writer_id при первой append; последующая
append того же scope ДРУГИМ writer-ом -> BlackboardContention (caller решает, как быть:
напр. прочитать snapshot и дописать под своим writer-ом, или отказаться).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from contracts.i_blackboard import (
    BlackboardContention,
    BlackboardEntry,
    BlackboardSnapshot,
    IBlackboard,
)


class InMemoryBlackboard(IBlackboard):
    """In-memory append-only versioned blackboard с single-writer-per-scope."""

    def __init__(self) -> None:
        self._entries: Dict[str, List[BlackboardEntry]] = {}
        self._writer: Dict[str, str] = {}  # scope -> текущий writer_id (single-writer)

    def append(self, scope: str, writer_id: str, payload: Any) -> BlackboardEntry:
        bucket = self._entries.setdefault(scope, [])
        # single-writer: если scope уже пишется другим writer-ом -> отказ
        current = self._writer.get(scope)
        if current is not None and current != writer_id:
            raise BlackboardContention(
                f"scope '{scope}' locked by writer '{current}', contested by '{writer_id}'"
            )
        self._writer[scope] = writer_id
        version = len(bucket) + 1
        entry = BlackboardEntry(
            version=version, scope=scope, writer_id=writer_id, payload=payload, seq=version
        )
        bucket.append(entry)
        return entry

    def snapshot(self, scope: str) -> BlackboardSnapshot:
        bucket = self._entries.get(scope)
        if bucket is None:
            raise KeyError  # caller ловит как scope-unknown
        return BlackboardSnapshot(scope=scope, version=len(bucket), entries=tuple(bucket))

    def latest_version(self, scope: str) -> int:
        bucket = self._entries.get(scope)
        return len(bucket) if bucket else 0

    def scopes(self) -> Tuple[str, ...]:
        return tuple(self._entries.keys())
