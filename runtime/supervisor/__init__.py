"""runtime.supervisor — Autonomous Runtime Recovery Layer (Phase 4).

Observe -> Decide -> Recover -> Verify. Depends ONLY on contracts + local runtime
modules + stdlib (arch-gate LAW K8). No services/adapters/plugins imports.
"""
from __future__ import annotations

from runtime.supervisor.supervisor_service import SupervisorService
from runtime.supervisor.health_monitor import HealthMonitor
from runtime.supervisor.recovery_policy import RecoveryPolicyRegistry
from runtime.supervisor.exceptions import (
    ComponentFailure,
    KernelPanic,
    RuntimeFailure,
    SupervisorError,
)

__all__ = [
    "SupervisorService",
    "HealthMonitor",
    "RecoveryPolicyRegistry",
    "ComponentFailure",
    "KernelPanic",
    "RuntimeFailure",
    "SupervisorError",
]
