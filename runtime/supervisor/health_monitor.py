"""Health Monitor — observe-only component health via the IProcessRegistry.

Per Phase 4: the monitor reads ProcessState from the registry and emits health
events on the IEventBus. It never mutates a component (no restart, no build) —
that is the Supervisor's job via IComponentController. Depends ONLY on contracts
+ stdlib (arch-gate LAW K8).

Healthy  == state in {RUNNING, DEGRADED}
Unhealthy== state in {FAILED, QUARANTINED}
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from contracts import IEventBus, IHealthCheck, IProcess, IProcessRegistry, ProcessState


class HealthMonitor:
    """Periodically inspects registry states and publishes health events."""

    def __init__(
        self,
        bus: IEventBus,
        registry: IProcessRegistry,
        health_check: Optional[IHealthCheck] = None,
        logger: Any = None,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._check = health_check
        self._log = logger

    def is_healthy(self, proc: IProcess) -> bool:
        if self._check is not None:
            return self._check.is_healthy(proc)
        return proc.state in (ProcessState.RUNNING, ProcessState.DEGRADED)

    def scan(self) -> Dict[str, str]:
        """Return {name: 'healthy'|'unhealthy'} for all registered processes."""
        report: Dict[str, str] = {}
        for name in self._registry.list():
            proc = self._registry.get(name)
            if proc is None:
                continue
            healthy = self.is_healthy(proc)
            report[name] = "healthy" if healthy else "unhealthy"
            if not healthy:
                self._bus.publish_sync("health.unhealthy", {
                    "name": name, "state": proc.state.value,
                })
                if self._log:
                    self._log.warn("health.unhealthy", name=name, state=proc.state.value)
        if self._log:
            self._log.info("health.scan", healthy=sum(1 for v in report.values() if v == "healthy"),
                           unhealthy=sum(1 for v in report.values() if v == "unhealthy"))
        return report
