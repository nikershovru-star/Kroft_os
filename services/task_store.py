"""Minimal in-memory TaskStore (ТЗ-DAILY-01) — real component, not seed.

K1-compliant: stdlib + contracts only. This is a NEW, narrow seam: there was NO existing TaskStore
to reuse (K5 verified). It holds real (task_id, status) pairs so the dashboard's Tasks surface
reflects genuine queued work instead of a hard-coded 0. The agent loop enqueues tasks here as it
processes queries (ТЗ-DAILY-01 Commit 3 wires the interactive contour); until then the store is
empty (0 queued) — which is the honest, live state.

The dashboard reads it via duck-typed `task_store.list()` (each item has `.id` / `.status`),
exactly as build_default_dashboard already supports (DESKTOP-01). No new dashboard port needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Task:
    """A single tracked task (ТЗ-DAILY-01)."""

    id: str
    status: str  # e.g. "queued", "running", "done", "failed"


class TaskStore:
    """In-memory store of real tasks (ТЗ-DAILY-01). Deterministic, stdlib-only."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}

    def add(self, task_id: str, status: str = "queued") -> Task:
        t = Task(id=task_id, status=status)
        self._tasks[task_id] = t
        return t

    def update(self, task_id: str, status: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id] = Task(id=task_id, status=status)

    def get(self, task_id: str) -> "Task | None":
        return self._tasks.get(task_id)

    def list(self) -> List[Task]:
        return [self._tasks[k] for k in sorted(self._tasks)]

    def count(self) -> int:
        return len(self._tasks)
