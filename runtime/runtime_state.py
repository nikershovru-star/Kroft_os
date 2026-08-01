"""Runtime State FSM — thin extension over the IKernel contract.

Does NOT import the concrete kernel (arch-gate: runtime.* -> contracts only).
Depends on `contracts.IKernel` (the port), not on `kernel.Kernel`. No second
kernel, no XxxWrapper adapters.
"""
from __future__ import annotations

from contracts import IKernel, LifecycleState


class RuntimeState:
    """State mirror over an IKernel implementation (injected, never imported)."""

    def __init__(self, kernel: IKernel) -> None:
        self._kernel = kernel
        self._ready = False
        self._paused = False
        self._failed = False
        self._stopped = False

    def mark_running(self) -> None:
        self._ready = True

    def mark_stopped(self) -> None:
        self._ready = False
        self._stopped = True

    def mark_failed(self) -> None:
        self._failed = True

    def is_ready(self) -> bool:
        return self._ready and self._kernel.state == LifecycleState.INITIALIZED

    def is_running(self) -> bool:
        return self._kernel.state == LifecycleState.RUNNING and not self._paused

    def is_paused(self) -> bool:
        return self._kernel.state == LifecycleState.RUNNING and self._paused

    def is_stopped(self) -> bool:
        return self._kernel.state == LifecycleState.STOPPED

    def is_failed(self) -> bool:
        return self._failed
