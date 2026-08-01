"""(services) ConfigApplier — two-phase apply with rollback (Wave 13, ADR-016 Phase E).

The ONLY component allowed to mutate a runtime target. Enforces the guardrail
lifecycle: `propose()` -> `approve()` -> `apply()`. `apply()` refuses unless the
rec was approved. Every apply writes a history entry (previous_value, new_value,
timestamp, approved_by) so `rollback()` can restore the prior state.

LAW 2: imports only contracts.* (IOptimizer/IGuardrail/Recommendation) — never
the concrete PatternBasedOptimizer/SimpleGuardrail.
LAW 3: history is explicit mutable state, owned here on purpose (not a hidden
global). Recommendations are frozen entities.
LAW 4: rollback restores exactly the previous_value captured at apply time.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from contracts.i_optimization import (
    REC_STATUS_APPLIED,
    REC_STATUS_APPROVED,
    REC_STATUS_PROPOSED,
    REC_STATUS_ROLLED_BACK,
    Recommendation,
)


@dataclass
class _ChangeRecord:
    rec_id: str
    target: str
    previous_value: Any
    new_value: Any
    timestamp: float
    approved_by: Optional[str]


class ConfigApplier:
    """Manual configuration applier with explicit history + rollback."""

    def __init__(self) -> None:
        # rec_id -> Recommendation (the proposed/approved entity)
        self._recs: Dict[str, Recommendation] = {}
        # rec_id -> approver label (set on approve)
        self._approved_by: Dict[str, str] = {}
        # chronological change log for rollback
        self._history: List[_ChangeRecord] = []

    # --- lifecycle --------------------------------------------------------
    def propose(self, rec: Recommendation) -> str:
        """Store a proposed recommendation, return its id."""
        self._recs[rec.id] = rec
        return rec.id

    def approve(self, rec_id: str, approved_by: str = "human") -> bool:
        """Mark a rec approved. Does NOT apply to runtime."""
        rec = self._recs.get(rec_id)
        if rec is None:
            return False
        self._recs[rec_id] = rec.__class__(**{**rec.__dict__, "status": REC_STATUS_APPROVED})
        self._approved_by[rec_id] = approved_by
        return True

    def apply(self, rec_id: str, target: Any) -> bool:
        """Apply `rec` to `target` (dict-like or attribute object).

        Requires a prior approve(). Two-phase commit — refuse otherwise.
        """
        rec = self._recs.get(rec_id)
        if rec is None or rec.status != REC_STATUS_APPROVED:
            return False

        prev = self._read(target, rec.target)
        try:
            new_val = json.loads(rec.value)
        except (json.JSONDecodeError, TypeError):
            new_val = rec.value
        self._write(target, rec.target, new_val)

        self._recs[rec_id] = rec.__class__(**{**rec.__dict__, "status": REC_STATUS_APPLIED})
        self._history.append(_ChangeRecord(
            rec_id=rec_id,
            target=rec.target,
            previous_value=prev,
            new_value=new_val,
            timestamp=time.time(),
            approved_by=self._approved_by.get(rec_id, "human"),
        ))
        return True

    def rollback(self, rec_id: str, target: Any) -> bool:
        """Restore the previous_value captured at the last apply() on `target`."""
        change = next((c for c in reversed(self._history) if c.rec_id == rec_id), None)
        if change is None:
            return False
        self._write(target, change.target, change.previous_value)
        rec = self._recs.get(rec_id)
        if rec is None:
            return False
        self._recs[rec_id] = rec.__class__(**{**rec.__dict__, "status": REC_STATUS_ROLLED_BACK})
        self._history.append(_ChangeRecord(
            rec_id=rec_id,
            target=change.target,
            previous_value=change.new_value,
            new_value=change.previous_value,
            timestamp=time.time(),
            approved_by="rollback",
        ))
        return True

    # --- history ----------------------------------------------------------
    def history(self) -> List[Dict]:
        return [
            {
                "rec_id": c.rec_id,
                "target": c.target,
                "previous_value": c.previous_value,
                "new_value": c.new_value,
                "timestamp": c.timestamp,
                "approved_by": c.approved_by,
            }
            for c in self._history
        ]

    def status(self, rec_id: str) -> Optional[str]:
        rec = self._recs.get(rec_id)
        return rec.status if rec else None

    # --- target path read/write (string-path resolver) -------------------
    @staticmethod
    def _read(target: Any, path: str) -> Any:
        """Resolve 'a:b:c' against a nested dict or attribute object."""
        parts = path.split(":")
        cur = target
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if isinstance(cur, dict):
                if last:
                    return cur.get(part)
                cur = cur.get(part, {})
            else:
                if last:
                    return getattr(cur, part, None)
                cur = getattr(cur, part, None)
        return None

    @staticmethod
    def _write(target: Any, path: str, value: Any) -> None:
        parts = path.split(":")
        cur = target
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if isinstance(cur, dict):
                if last:
                    cur[part] = value
                else:
                    cur = cur.setdefault(part, {})
            else:
                if last:
                    setattr(cur, part, value)
                else:
                    cur = getattr(cur, part)
