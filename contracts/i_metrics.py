"""IMetricsCollector port — runtime services depend on this, not on psutil.

Per LAW K8: `runtime.*` may import ONLY `contracts.*` (+stdlib). It cannot import
`psutil` directly (third-party, not a project package -> arch-gate would fail).
So the metrics source is a port; the concrete implementation (PsutilMetricsCollector)
lives in `infrastructure` (which may import third-party libs) and is injected by the
composition root.
"""
from __future__ import annotations

from typing import Dict, Protocol, runtime_checkable


@runtime_checkable
class IMetricsCollector(Protocol):
    """Collects runtime metrics (cpu %, memory %, ...). Returns a flat dict."""

    def collect(self) -> Dict[str, float]:
        """Return current metric values keyed by name (e.g. {'cpu': 12.3})."""
        ...
