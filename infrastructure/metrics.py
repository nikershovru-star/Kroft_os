"""Concrete metrics collector (infrastructure layer).

Per LAW K8: `runtime.*` may import ONLY `contracts.*`, so it cannot import `psutil`
directly. The `IMetricsCollector` port lives in `contracts`; this implementation
(in `infrastructure`, which may use third-party libs) wraps `psutil` and is injected
into `MetricsService` by the composition root.
"""
from __future__ import annotations

from typing import Any, Dict

from contracts import IMetricsCollector


class PsutilMetricsCollector(IMetricsCollector):
    """Collects CPU % and memory % via psutil (graceful if unavailable)."""

    def __init__(self, pid: int | None = None) -> None:
        self._pid = pid
        try:
            import psutil  # type: ignore
            self._psutil = psutil
            self._proc = psutil.Process(pid) if pid else None
        except Exception:
            self._psutil = None
            self._proc = None

    def collect(self) -> Dict[str, float]:
        if self._psutil is None:
            return {"cpu": 0.0, "memory": 0.0}
        try:
            cpu = self._psutil.cpu_percent(interval=None)
            if self._proc is not None:
                mem = self._proc.memory_percent()
            else:
                mem = self._psutil.virtual_memory().percent
            return {"cpu": float(cpu), "memory": float(mem)}
        except Exception:
            return {"cpu": 0.0, "memory": 0.0}
