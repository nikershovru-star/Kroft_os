"""runtime.services — Runtime Services (Observability Foundation, Phase 3).

Observer services that hang on the IEventBus. They depend ONLY on contracts
(+stdlib) and never import domain platforms (LAW K3 / LAW K8). Each is wired by
the composition root (bootstrap_v2.py) which injects the concrete IEventBus /
IMetricsCollector / IProcessRegistry implementations.
"""
from __future__ import annotations

from runtime.services.logging_service import LoggingService
from runtime.services.metrics_service import MetricsService
from runtime.services.config_service import ConfigService
from runtime.services.snapshot_service import SnapshotService

__all__ = [
    "LoggingService",
    "MetricsService",
    "ConfigService",
    "SnapshotService",
]
