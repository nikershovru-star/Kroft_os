"""IProcess port — the process/component contract for the Runtime Host.

Per ADR-020 (variant b) and Master Dev Plan v2.0 Phase 2/4: the Kernel sees ONLY
IProcess. Platforms 11–14 integrate as components through this port — never as
concrete platform classes. `pid` is a UUID (not an OS PID). Lifecycle is driven
through the port, not by reaching into the platform.

Phase 4 extends the status enum into a full ProcessState machine
(REGISTERED/STARTING/RUNNING/DEGRADED/STOPPING/STOPPED/FAILED/RECOVERING/QUARANTINED)
and adds IComponentController (Supervisor restarts via the port — it never knows
how an instance is built, where the manifest lives, or which platform it is) and
IHealthCheck (observe-only health signal).

This is a contracts.* port, so `runtime.*` may import it (arch-gate LAW K8).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class ProcessState(Enum):
    """Full process lifecycle state machine (Phase 4)."""

    REGISTERED = "REGISTERED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"


# Backwards-compatible alias (Phase 2/3 code referenced ProcessStatus).
ProcessStatus = ProcessState


@runtime_checkable
class IProcess(Protocol):
    """A runtime component the Kernel controls through the port only."""

    @property
    def pid(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def state(self) -> ProcessState: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def restart(self) -> bool: ...


@runtime_checkable
class IProcessRegistry(Protocol):
    """Registry of IProcess components (NOT concrete platforms)."""

    def register(self, process: IProcess) -> None: ...

    def get(self, name: str) -> Optional[IProcess]: ...

    def list(self) -> list[str]: ...

    def kill(self, name: str) -> None: ...


@runtime_checkable
class IHealthCheck(Protocol):
    """Observe-only health signal for a component (no mutation)."""

    def is_healthy(self, process: IProcess) -> bool: ...


@runtime_checkable
class IComponentController(Protocol):
    """Restart abstraction — Supervisor calls this, knows nothing about building.

    The concrete implementation (composition root) wires ComponentRegistry +
    InstanceBuilder. The Supervisor only sees this port (LAW K8 preserved).
    """

    def restart(self, component_name: str) -> bool:
        """Attempt to restart a component. Returns True if it came back RUNNING."""
        ...
