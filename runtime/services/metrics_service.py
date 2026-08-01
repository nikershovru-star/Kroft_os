"""MetricsService — collects lifecycle/health metrics and publishes to IEventBus.

Per Phase 3: observes component lifecycle (start/stop/fail) via the event bus and
publishes metrics (cpu/memory/counters) periodically. Depends ONLY on contracts
(IEventBus, IMetricsCollector, IProcessRegistry) + stdlib (arch-gate LAW K8).
Does NOT import platforms. No print — uses LoggingService.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from contracts import IEventBus, IMetricsCollector, IProcessRegistry, ProcessStatus


class MetricsService:
    """Periodically samples metrics and republishes them as `metric:*` events."""

    def __init__(
        self,
        bus: IEventBus,
        collector: Optional[IMetricsCollector] = None,
        registry: Optional[IProcessRegistry] = None,
        interval_sec: float = 5.0,
        logger: Any = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._bus = bus
        self._collector = collector
        self._registry = registry
        self._interval = interval_sec
        self._log = logger
        self._sleep = sleep_fn
        self._counters: Dict[str, int] = {"started": 0, "stopped": 0, "failed": 0}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        bus.subscribe("kernel.lifecycle", self._on_lifecycle)
        bus.subscribe("component.lifecycle", self._on_component)

    # --- event handlers (observe, never mutate platforms) ------------------
    def _on_lifecycle(self, event: dict) -> None:
        kind = event.get("type", "")
        if self._log:
            self._log.info("kernel.lifecycle", type=kind)

    def _on_component(self, event: dict) -> None:
        status = event.get("status", "")
        with self._lock:
            if status == "RUNNING":
                self._counters["started"] += 1
            elif status == "STOPPED":
                self._counters["stopped"] += 1
            elif status == "FAILED":
                self._counters["failed"] += 1
        if self._log:
            self._log.info("component.lifecycle", name=event.get("name"), status=status)

    # --- sampling loop -----------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="metrics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while self._running:
            self._publish_snapshot()
            self._sleep(self._interval)

    def _publish_snapshot(self) -> None:
        snap: Dict[str, Any] = dict(self._counters)
        if self._collector is not None:
            snap.update(self._collector.collect())
        if self._registry is not None:
            snap["components_total"] = len(self._registry.list())
            snap["components_running"] = sum(
                1 for n in self._registry.list()
                if (self._registry.get(n) is not None
                    and getattr(self._registry.get(n), "state", None) == ProcessStatus.RUNNING)
            )
        self._bus.publish_sync("metric:snapshot", snap)
        # Backward-compatible single metric topics (used by smoke test).
        if "cpu" in snap:
            self._bus.publish_sync("metric:cpu", {"cpu": snap["cpu"]})
        if "memory" in snap:
            self._bus.publish_sync("metric:memory", {"memory": snap["memory"]})
        if self._log:
            self._log.info("metric:snapshot", **snap)
