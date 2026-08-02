"""Telemetry sink port — time-series metrics (TZ-OBS-001, ADR-040).

K1-compliant: stdlib only. NOTE: this is SEPARATE from contracts.i_metrics
.IMetricsCollector (which is system metrics: collect() -> Dict[str,float]).
ITelemetrySink is for time-series recording/querying of event-derived metrics
(circuit.trip, sandbox.kill, degradation.level, ...).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple


@dataclass(frozen=True)
class MetricPoint:
    """A single time-series sample."""

    timestamp: float  # epoch seconds
    value: float
    tags: FrozenSet[Tuple[str, str]] = frozenset()


class ITelemetrySink(ABC):
    """Time-series metric store (record / query / snapshot)."""

    @abstractmethod
    def record(self, metric: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Append a sample for `metric`."""

    @abstractmethod
    def query(self, metric: str, window_sec: float) -> List[MetricPoint]:
        """Return samples for `metric` within the last `window_sec` seconds."""

    @abstractmethod
    def snapshot(self) -> Dict[str, List[MetricPoint]]:
        """Return all retained samples keyed by metric name."""

    # --- convenience aggregations (default impls may override) ------------
    def aggregate(self, metric: str, window_sec: float) -> Dict[str, float]:
        """count/sum/avg/max/min over `window_sec`."""
        pts = self.query(metric, window_sec)
        if not pts:
            return {"count": 0.0, "sum": 0.0, "avg": 0.0, "max": 0.0, "min": 0.0}
        vals = [p.value for p in pts]
        return {
            "count": float(len(vals)),
            "sum": float(sum(vals)),
            "avg": float(sum(vals) / len(vals)),
            "max": float(max(vals)),
            "min": float(min(vals)),
        }
