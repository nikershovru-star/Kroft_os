"""ExecutionTape — append-only execution trace for deterministic replay.

Minimal implementation intended for observability and replay, not a full
event-sourcing system. Each record is a frozen dataclass; the tape itself is
an append-only list persisted as JSONL.

K1-compliant: stdlib + contracts only.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ExecutionRecord:
    """One recorded agent execution step."""

    step_id: str
    episode_id: str
    cycle_id: str
    fsm_state: str
    transition: str
    goal: str
    action: str
    result: str
    confidence: float = 0.0
    errors: Tuple[str, ...] = ()
    tool_failures: Tuple[str, ...] = ()
    planning_failures: int = 0
    execution_failures: int = 0
    retrieval_quality: float = 0.0
    reasoning_outcome: str = ""
    learning_outcome: str = ""
    cycle_duration: float = 0.0
    retry_count: int = 0
    thrash_count: int = 0
    repeated_action: bool = False
    repeated_failure: bool = False
    timestamp: float = field(default_factory=time.time)


class ExecutionTape:
    """Append-only execution tape backed by JSONL file."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._records: List[ExecutionRecord] = []
        self._path = Path(path) if path else None

    def record(self, record: ExecutionRecord) -> None:
        self._records.append(record)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    def episode(self, episode_id: str) -> List[ExecutionRecord]:
        return [r for r in self._records if r.episode_id == episode_id]

    def replay(self, episode_id: str) -> List[dict]:
        return [r.__dict__ for r in self.episode(episode_id)]

    def load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                data["errors"] = tuple(data.get("errors", ()))
                data["tool_failures"] = tuple(data.get("tool_failures", ()))
                self._records.append(ExecutionRecord(**data))

    def __len__(self) -> int:
        return len(self._records)
