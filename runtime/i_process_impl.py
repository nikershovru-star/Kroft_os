"""Concrete IProcess implementation — the Runtime Host's view of a component.

Per ADR-020 / Phase 2/4: the Kernel sees ONLY IProcess. This class wraps an optional
underlying instance (a platform component supplied by the composition root) and drives
its lifecycle through the port. Duck-typing: if the instance has `run()`, the process
start() calls it in a worker thread; if not, start() is a no-op (LAW K3 — platforms
are NOT modified to gain start/stop; we adapt, not mutate).

Phase 4: full ProcessState FSM. On an exception from the run-loop the process goes
FAILED (not silently). `restart()` drives RECOVERING -> RUNNING (or QUARANTINED if the
recovery policy says give up). The Supervisor triggers restart via IComponentController;
this class only models the state, it never builds new instances (LAW K8 preserved).

pid is a UUID (never an OS PID). Imports ONLY contracts (arch-gate LAW K8).
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

from contracts import IProcess, ProcessState


class Process(IProcess):
    """IProcess implementation wrapping an optional platform component instance."""

    def __init__(
        self,
        name: str,
        instance: Any = None,
        capabilities: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        sleep_fn=None,
    ) -> None:
        self._pid = uuid.uuid4().hex
        self._name = name
        self._instance = instance
        self._capabilities = list(capabilities or [])
        self._dependencies = list(dependencies or [])
        self._state = ProcessState.REGISTERED
        self._thread: Optional[threading.Thread] = None
        self._sleep = sleep_fn or (lambda s: None)  # injectable for tests
        self._last_error: Optional[str] = None

    @property
    def pid(self) -> str:
        return self._pid

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ProcessState:
        return self._state

    @property
    def instance(self) -> Any:
        return self._instance

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def start(self) -> None:
        if self._state in (ProcessState.RUNNING, ProcessState.STARTING):
            return
        self._state = ProcessState.STARTING
        self._state = ProcessState.RUNNING  # synchronous start for component wrappers
        # Duck-typing: run the component's run() loop if present (CPU-bound platforms).
        if self._instance is not None and hasattr(self._instance, "run"):
            def _loop():
                try:
                    if hasattr(self._instance, "run") and _accepts_no_args(self._instance.run):
                        self._instance.run()
                    else:
                        while self._state == ProcessState.RUNNING:
                            self._sleep(0.5)
                except Exception as exc:  # component crashed -> FAILED (Phase 4)
                    self._last_error = str(exc)
                    self._state = ProcessState.FAILED
            self._thread = threading.Thread(target=_loop, name=f"proc-{self._name}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._state = ProcessState.STOPPING
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._state = ProcessState.STOPPED

    def pause(self) -> None:
        if self._state == ProcessState.RUNNING:
            self._state = ProcessState.DEGRADED

    def resume(self) -> None:
        if self._state == ProcessState.DEGRADED:
            self._state = ProcessState.RUNNING

    def restart(self) -> bool:
        """Drive RECOVERING -> RUNNING. Returns True if it came back alive.

        Does NOT build a new instance; the Supervisor (via IComponentController)
        is responsible for re-creating the underlying instance if needed. This
        method only models the state transition for an already-rebuilt instance.
        """
        if self._state == ProcessState.QUARANTINED:
            return False
        self._state = ProcessState.RECOVERING
        self.start()
        return self._state == ProcessState.RUNNING

    def bind_instance(self, instance: Any) -> None:
        """Composition root attaches the real platform instance post-construction."""
        self._instance = instance


def _accepts_no_args(fn) -> bool:
    import inspect
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return False
    params = [p for p in sig.parameters.values()
              if p.default is inspect.Parameter.empty and p.kind in (
                  inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)]
    return len(params) == 0
