"""Observability port for live runtime metrics (ТЗ-OBS-01, ADR-067).

K1-compliant: stdlib + contracts only.

NOTE (ТЗ-OBS-01 K5 baseline correction): ``contracts/i_metrics.py`` already defines a
DIFFERENT ``IMetricsCollector`` (system metrics: cpu/memory % for the psutil boundary,
KROFT one-port-per-boundary). We do NOT reuse/override that name. This module owns the
OBSERVABILITY boundary: a ``ILiveMetricsCollector`` that accumulates *operational*
counters (execution outcomes, federation delivery, memory consolidation, LLM fallback)
and exposes them as RATIOS (Флаг 1) so the RT-01 reflection rules (R1/R3 compare against
fractions) fire correctly.

The collector stores a numerator + denominator per metric and computes the ratio on
``collect``/``snapshot``. ``memory.consolidation_confidence`` is derived from a sliding
window of outcome utilities (Флаг 2) — never undefined when consolidation is sparse.
"""

from __future__ import annotations

from typing import Dict, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Canonical metric names (must match RT-01 reflection rule names exactly)
# ---------------------------------------------------------------------------
METRIC_EXECUTION_SUCCESS_RATE = "execution.success_rate"
METRIC_FEDERATION_DELIVERY_SUCCESS_RATE = "federation.delivery_success_rate"
METRIC_MEMORY_GROWTH_RATE_PER_TICK = "memory.growth_rate_per_tick"
METRIC_MEMORY_CONSOLIDATION_CONFIDENCE = "memory.consolidation_confidence"
METRIC_LLM_FALLBACK_RATE = "llm.fallback_rate"

# Canonical metric names for the SOFT-tunable CURRENT values the supervisor reads back
# (mirrors build_runtime_metrics in kernel/runtime_supervisor.py)
METRIC_NETWORK_CONNECT_TIMEOUT_CURRENT = "network.ensure_connected_timeout.current"
METRIC_MEMORY_MIN_REPETITIONS_CURRENT = "memory.min_repetitions.current"
METRIC_MEMORY_CONFIDENCE_THRESHOLD_CURRENT = "memory.confidence_threshold.current"


@runtime_checkable
class ILiveMetricsCollector(Protocol):
    """Accumulates operational counters and exposes them as RATIOS (Флаг 1).

    Implementations store numerator + denominator per metric and compute the ratio on
    read. Hooks in the kernel call the ``record_*`` helpers; consumers call
    ``snapshot`` (name -> ratio) or ``counts`` (raw numerator/denominator).
    """

    def record_attempt(self, metric: str) -> None:
        """Increment the denominator for ``metric`` (an observed opportunity)."""
        ...

    def record_success(self, metric: str) -> None:
        """Increment both numerator and denominator for ``metric`` (a success)."""
        ...

    def record_failure(self, metric: str) -> None:
        """Increment only the denominator for ``metric`` (a failure)."""
        ...

    def record_raw(self, metric: str, value: float) -> None:
        """Push a raw sliding-window sample (e.g. outcome utility for consolidation)."""
        ...

    def record_episode_growth(self, n: int) -> None:
        """Add ``n`` new episodes this tick (for memory.growth_rate_per_tick)."""
        ...

    def record_tick(self) -> None:
        """Advance the tick window (for per-tick rates)."""
        ...

    def ratio(self, metric: str) -> float:
        """Return the computed ratio for ``metric`` (0.0 if undefined/empty)."""
        ...

    def last(self, metric: str) -> float:
        """Return the last computed ratio (carry-last semantics for sparse metrics)."""
        ...

    def snapshot(self) -> Dict[str, float]:
        """Return name -> current ratio for all known metrics."""
        ...

    def reset(self) -> None:
        """Clear all counters (test isolation)."""
        ...
