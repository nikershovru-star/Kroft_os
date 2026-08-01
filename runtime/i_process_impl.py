"""Concrete IProcess implementation — the Runtime Host's view of a component.

Per ADR-020 / Phase 2: the Kernel sees ONLY IProcess. This class wraps an optional
underlying instance (a platform component supplied by the composition root) and drives
its lifecycle through the port. Duck-typing: if the instance has `run()`, the process
start() calls it in a worker thread; if not, start() is a no-op (LAW K3 — platforms
are NOT modified to gain start/stop; we adapt, not mutate).

pid is a UUID (never an OS PID). Imports ONLY contracts (arch-gate LAW K8).
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

from contracts import IProcess, ProcessStatus


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
        self._status = ProcessStatus.UNBOUND
        self._thread: Optional[threading.Thread] = None
        self._sleep = sleep_fn or (lambda s: None)  # injectable for tests

    @property
    def pid(self) -> str:
        return self._pid

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ProcessStatus:
        return self._status

    @property
    def instance(self) -> Any:
        return self._instance

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def start(self) -> None:
        if self._status == ProcessStatus.RUNNING:
            return
        self._status = ProcessStatus.RUNNING
        # Duck-typing: run the component's run() loop if present (CPU-bound platforms).
        if self._instance is not None and hasattr(self._instance, "run"):
            def _loop():
                try:
                    # Some platforms expose run(goal); without a goal we call no-arg
                    # if available, else mark running and idle.
                    if hasattr(self._instance, "run") and _accepts_no_args(self._instance.run):
                        self._instance.run()
                    else:
                        # Idle: keep process alive until stop() flips status.
                        while self._status == ProcessStatus.RUNNING:
                            self._sleep(0.5)
                except Exception:
                    self._status = ProcessStatus.FAILED
            self._thread = threading.Thread(target=_loop, name=f"proc-{self._name}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._status = ProcessStatus.STOPPED
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def pause(self) -> None:
        if self._status == ProcessStatus.RUNNING:
            self._status = ProcessStatus.PAUSED

    def resume(self) -> None:
        if self._status == ProcessStatus.PAUSED:
            self._status = ProcessStatus.RUNNING

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
