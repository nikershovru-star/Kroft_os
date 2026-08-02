"""In-memory telemetry sink (TZ-OBS-001, ADR-040).

K8-compliant: lives in adapters/ (infra). Imports ONLY contracts + stdlib.
Thread-safe ring buffer per metric; RAM-only (honest v1 limitation: lost on
restart). Provides count/sum/avg/max/min aggregation over a sliding window.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from contracts.i_telemetry import ITelemetrySink, MetricPoint


class InMemoryTelemetrySink(ITelemetrySink):
    """Bounded in-RAM time-series store."""

    def __init__(self, capacity: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        self._capacity = capacity
        self._clock = clock
        self._lock = threading.Lock()
        self._bufs: Dict[str, "deque[MetricPoint]"] = {}

    def record(self, metric: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        point = MetricPoint(
            timestamp=self._clock(),
            value=value,
            tags=frozenset((k, v) for k, v in (tags or {}).items()),
        )
        with self._lock:
            buf = self._bufs.get(metric)
            if buf is None:
                buf = deque(maxlen=self._capacity)
                self._bufs[metric] = buf
            buf.append(point)

    def query(self, metric: str, window_sec: float) -> List[MetricPoint]:
        with self._lock:
            buf = self._bufs.get(metric)
            if not buf:
                return []
            cutoff = self._clock() - window_sec
            return [p for p in buf if p.timestamp >= cutoff]

    def snapshot(self) -> Dict[str, List[MetricPoint]]:
        with self._lock:
            return {m: list(buf) for m, buf in self._bufs.items()}

    # convenience aggregation already provided by ITelemetrySink base.
