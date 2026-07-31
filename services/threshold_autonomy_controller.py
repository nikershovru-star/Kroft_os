"""(services) ThresholdAutonomyController — IAutonomyController (Wave 14, ADR-017).

Decides WHEN to run a retrospective. v0.1: triggers when enough traces have
accumulated OR enough wall-clock time passed since the last run. Keeps explicit
mutable state (LAW 3) — no hidden globals — and is rate-limited to protect
against loop autonomy (ADR-017 §Риски).

LAW 2: imports only contracts.* + stdlib.
"""
from __future__ import annotations

import time
from typing import Dict, List

from contracts.i_learning import ExecutionTrace
from contracts.i_autonomy import IAutonomyController

# rate-limit: at most one retrospective per this many seconds (loop protection)
DEFAULT_MIN_INTERVAL_S = 3600  # 1 hour


class ThresholdAutonomyController(IAutonomyController):
    """Trigger on trace count OR elapsed time since last retrospective."""

    def __init__(
        self,
        min_traces: int = 5,
        min_interval_s: int = DEFAULT_MIN_INTERVAL_S,
    ) -> None:
        self._min_traces = min_traces
        self._min_interval_s = min_interval_s
        # explicit mutable state (LAW 3) — not a hidden global
        self._last_retrospect_at: float = 0.0
        self._retrospect_count: int = 0

    def should_retrospect(self, traces: List[ExecutionTrace], config: Dict) -> bool:
        count = len(traces)
        now = time.time()
        elapsed = now - self._last_retrospect_at
        enough_traces = count >= self._min_traces
        enough_time = elapsed >= self._min_interval_s
        if enough_traces and enough_time:
            # mark the attempt so we don't spin (rate-limit)
            self._last_retrospect_at = now
            self._retrospect_count += 1
            return True
        return False

    # --- introspection (explicit state) ----------------------------------
    def last_retrospect_at(self) -> float:
        return self._last_retrospect_at

    def retrospect_count(self) -> int:
        return self._retrospect_count
