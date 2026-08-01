"""Recovery Journal — append-only log of every recovery attempt.

Per Phase 4 (mandatory addition): each recovery writes a structured record so that,
months later, the OS can reason about failure patterns ("MetricsService crashes
every 3 days after 6h of uptime"). This is the foundation of self-analysis.

Record shape:
  {"component": "MetricsService", "failure": "ConnectionError",
   "attempt": 2, "timestamp": "2026-08-01T15:00", "result": "success"}

Imports ONLY contracts + stdlib (arch-gate LAW K8). Rotation via stdlib logging-free
JSON append (one object per line) — no third-party deps.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class RecoveryJournal:
    """Append-only JSON journal of recovery attempts."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else (Path.cwd() / "recovery_journal.jsonl")
        self._records: List[Dict[str, Any]] = []

    def record(
        self,
        component: str,
        failure: str,
        attempt: int,
        result: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "component": component,
            "failure": failure,
            "attempt": attempt,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "result": result,
        }
        if extra:
            entry.update(extra)
        self._records.append(entry)
        self._append_line(entry)
        return entry

    def _append_line(self, entry: Dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # journal must never break recovery

    def recent(self, component: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        recs = self._records
        if component is not None:
            recs = [r for r in recs if r.get("component") == component]
        return recs[-limit:]

    def load(self) -> List[Dict[str, Any]]:
        """Re-read the on-disk journal (for self-analysis across restarts)."""
        if not self._path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        except Exception:
            pass
        self._records = out
        return out
