"""Live observability reference impl (ТЗ-OBS-01, ADR-067) — LLM-free, K1.

Provides:
- ``LiveMetricsCollector``: accumulates operational counters as RATIOS (Флаг 1) with a
  sliding window for sparse metrics (Флаг 2). This is the reference impl of
  ``ILiveMetricsCollector`` (contracts/i_observability.py) — the OBSERVABILITY boundary,
  SEPARATE from contracts/i_metrics.py system metrics (one-port-per-boundary).
- ``LiveRuntimeMetrics(IRuntimeMetrics)``: feeds the RT-01 RuntimeSupervisor from LIVE
  counters instead of an injectable snapshot (closes the RT-01 debt: autonomous
  adaptation). ``ReferenceRuntimeMetrics`` (injectable) is preserved for RT-01 tests.

Hook contract: the kernel calls ``record_*`` helpers on a collector; when no collector
is wired, hooks are no-ops (kernel behavior unchanged — ТЗ-OBS-01 constraint).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
)
from contracts.i_observability import (
    ILiveMetricsCollector,
    METRIC_EXECUTION_SUCCESS_RATE,
    METRIC_FEDERATION_DELIVERY_SUCCESS_RATE,
    METRIC_LLM_FALLBACK_RATE,
    METRIC_MEMORY_CONFIDENCE_THRESHOLD_CURRENT,
    METRIC_MEMORY_CONSOLIDATION_CONFIDENCE,
    METRIC_MEMORY_GROWTH_RATE_PER_TICK,
    METRIC_MEMORY_MIN_REPETITIONS_CURRENT,
    METRIC_NETWORK_CONNECT_TIMEOUT_CURRENT,
)
from contracts.i_runtime_reflection import IRuntimeMetrics, RuntimeMetric

_Window_SIZE = 32  # sliding window for sparse/ratio metrics (Флаг 2/3)


class LiveMetricsCollector:
    """Reference impl of ILiveMetricsCollector. Stores num/den per metric and computes
    RATIOS on read (Флаг 1). Sparse metrics (consolidation confidence) use a sliding
    window of raw samples with carry-last (Флаг 2)."""

    def __init__(self, clock: Optional[NodeLamportClock] = None) -> None:
        self._clock = clock if clock is not None else NodeLamportClock("obs")
        self._num: Dict[str, float] = {}
        self._den: Dict[str, float] = {}
        self._window: Dict[str, Deque[float]] = {}
        self._last: Dict[str, float] = {}
        # per-tick growth accounting (Флаг 1: growth_rate_per_tick = episodes/ticks)
        self._tick_count: int = 0
        self._episode_acc: float = 0.0
        self._tick_episode_window: Deque[float] = deque(maxlen=_Window_SIZE)

    # -- raw record helpers (called by kernel hooks) --
    def record_attempt(self, metric: str) -> None:
        self._den[metric] = self._den.get(metric, 0.0) + 1.0

    def record_success(self, metric: str) -> None:
        self._num[metric] = self._num.get(metric, 0.0) + 1.0
        self._den[metric] = self._den.get(metric, 0.0) + 1.0

    def record_failure(self, metric: str) -> None:
        self._den[metric] = self._den.get(metric, 0.0) + 1.0

    def record_raw(self, metric: str, value: float) -> None:
        w = self._window.setdefault(metric, deque(maxlen=_Window_SIZE))
        w.append(float(value))
        self._last[metric] = float(value)

    def record_episode_growth(self, n: int) -> None:
        self._episode_acc += float(n)

    def record_tick(self) -> None:
        """Advance the tick window; snapshot per-tick episode growth."""
        self._tick_count += 1
        self._tick_episode_window.append(self._episode_acc)
        self._episode_acc = 0.0
        # carry-last for ratio metrics so they are never undefined (Флаг 2)
        for m in list(self._num.keys()):
            self._last[m] = self.ratio(m)

    # -- read helpers --
    def ratio(self, metric: str) -> float:
        if metric == METRIC_MEMORY_CONSOLIDATION_CONFIDENCE:
            return self._consolidation_confidence()
        if metric == METRIC_MEMORY_GROWTH_RATE_PER_TICK:
            return self._growth_rate_per_tick()
        den = self._den.get(metric, 0.0)
        if den <= 0.0:
            return self._last.get(metric, 0.0)
        return self._num.get(metric, 0.0) / den

    def _consolidation_confidence(self) -> float:
        """Avg outcome utility over the sliding window (Флаг 2): defined even when
        consolidation is sparse (degraded scenario). Empty window -> carry-last; if no
        history, neutral 0.5 (does not falsely trigger R3 on silence)."""
        w = self._window.get(METRIC_MEMORY_CONSOLIDATION_CONFIDENCE)
        if w:
            return sum(w) / len(w)
        return self._last.get(METRIC_MEMORY_CONSOLIDATION_CONFIDENCE, 0.5)

    def _growth_rate_per_tick(self) -> float:
        wins = list(self._tick_episode_window)
        ticks = len(wins)
        if ticks <= 0:
            return self._last.get(METRIC_MEMORY_GROWTH_RATE_PER_TICK, 0.0)
        return sum(wins) / ticks

    def last(self, metric: str) -> float:
        return self._last.get(metric, self.ratio(metric))

    def snapshot(self) -> Dict[str, float]:
        return {m: self.ratio(m) for m in set(self._num) | set(self._window) | {METRIC_MEMORY_CONSOLIDATION_CONFIDENCE, METRIC_MEMORY_GROWTH_RATE_PER_TICK}}

    def reset(self) -> None:
        self._num.clear()
        self._den.clear()
        self._window.clear()
        self._last.clear()
        self._tick_count = 0
        self._episode_acc = 0.0
        self._tick_episode_window.clear()


class LiveRuntimeMetrics(IRuntimeMetrics):
    """IRuntimeMetrics impl that reads LIVE counters (Флаг 1/2) instead of an injectable
    snapshot. Closes the RT-01 debt: RuntimeSupervisor now adapts autonomously from live
    operational signals. ``ReferenceRuntimeMetrics`` (injectable) remains for RT-01 tests.

    ``collect()`` mirrors ``build_runtime_metrics``: it emits current tunable values
    (read from the live targets) so reflection proposals carry honest old->new, plus the
    live operational ratios from the collector.
    """

    def __init__(self,
                 collector: ILiveMetricsCollector,
                 memory_evolution: Optional[object] = None,
                 network_transport: Optional[object] = None,
                 clock: Optional[NodeLamportClock] = None) -> None:
        self._collector = collector
        self._memory_evolution = memory_evolution
        self._network_transport = network_transport
        self._clock = clock if clock is not None else NodeLamportClock("live_metrics")

    def collect(self) -> List[RuntimeMetric]:
        mark = self._clock.tick()
        cs = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        out: List[RuntimeMetric] = []
        snap = self._collector.snapshot()
        for name, value in snap.items():
            out.append(RuntimeMetric(name, float(value), cs, mark))
        # current tunable values (honest old->new for proposals)
        if self._network_transport is not None and hasattr(self._network_transport, "_connect_timeout"):
            out.append(RuntimeMetric(METRIC_NETWORK_CONNECT_TIMEOUT_CURRENT,
                                     float(self._network_transport._connect_timeout), cs, mark))
        if self._memory_evolution is not None:
            if hasattr(self._memory_evolution, "_min_rep"):
                out.append(RuntimeMetric(METRIC_MEMORY_MIN_REPETITIONS_CURRENT,
                                         float(self._memory_evolution._min_rep), cs, mark))
            if hasattr(self._memory_evolution, "_thr"):
                out.append(RuntimeMetric(METRIC_MEMORY_CONFIDENCE_THRESHOLD_CURRENT,
                                         float(self._memory_evolution._thr), cs, mark))
        return out
