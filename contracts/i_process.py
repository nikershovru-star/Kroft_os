"""IProcess port — the minimal process/component contract for the Runtime Host.

Per ADR-020 (variant b) and Master Dev Plan v2.0 Phase 2: the Kernel sees ONLY
IProcess. Platforms 11–14 integrate as components through this port — never as
concrete platform classes. `pid` is a UUID (not an OS PID). Lifecycle is driven
through the port, not by reaching into the platform.

This is a contracts.* port, so `runtime.*` may import it (arch-gate LAW K8).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class ProcessStatus(Enum):
    UNBOUND = "UNBOUND"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"


@runtime_checkable
class IProcess(Protocol):
    """A runtime component the Kernel controls through the port only."""

    @property
    def pid(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def status(self) -> ProcessStatus: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


@runtime_checkable
class IProcessRegistry(Protocol):
    """Registry of IProcess components (NOT concrete platforms)."""

    def register(self, process: IProcess) -> None: ...

    def get(self, name: str) -> Optional[IProcess]: ...

    def list(self) -> list[str]: ...

    def kill(self, name: str) -> None: ...
