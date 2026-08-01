"""Kernel port — the minimal contract the Runtime Host depends on.

Per ADR-020 (variant b, accepted): `runtime.*` may import ONLY `contracts.*`.
It must NOT import the concrete `kernel` package. Instead it depends on this
`IKernel` protocol, and the concrete `Kernel` (in `kernel/kernel.py`) implements it.
The composition root (bootstrap_v2.py, outside the scanned packages) wires the
concrete `Kernel` into the runtime — no second kernel, no wrapper adapters.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class LifecycleState(Enum):
    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


@runtime_checkable
class IKernel(Protocol):
    """Minimal kernel contract for the Runtime Host (component layer)."""

    @property
    def state(self) -> LifecycleState: ...

    def initialize(self) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def emit(self, event_type: str, payload: Optional[dict] = None) -> None: ...

    def save(self) -> None: ...
