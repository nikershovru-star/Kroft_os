"""KnowledgeOS v5 Kernel — lifecycle orchestrator.

The kernel owns a single DependencyContainer (the composition root) and
drives a strict lifecycle state machine. It does NOT import concrete
adapters; everything is resolved through the container.
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Any, Dict, Optional

from infrastructure import DependencyContainer
from contracts import ICapabilityRegistry
from runtime import RuntimeContext


class LifecycleState(Enum):
    UNINITIALIZED = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    STOPPED = auto()


class Kernel:
    """Microkernel: composition root + lifecycle state machine."""

    def __init__(self, container: Optional[DependencyContainer] = None) -> None:
        self.container = container if container is not None else DependencyContainer()
        self._state = LifecycleState.UNINITIALIZED
        self._services: Dict[str, Any] = {}
        self.runtime_context: Optional[RuntimeContext] = None
        # Core capabilities resolved from the container during initialize().
        self.wired: Dict[str, Any] = {}

    @property
    def state(self) -> LifecycleState:
        return self._state

    def initialize(self) -> None:
        """Resolve core capabilities from the container and wire them in."""
        if self._state != LifecycleState.UNINITIALIZED:
            raise RuntimeError(f"initialize() called in {self._state.name}")
        self.runtime_context = RuntimeContext()
        for cap_name in ("ICapabilityRegistry", "IFileSystem"):
            if self.container.has(cap_name):
                self.wired[cap_name] = self.container.resolve(cap_name)
        if "ICapabilityRegistry" in self.wired:
            self.runtime_context.capabilities = self.wired["ICapabilityRegistry"]
        self._state = LifecycleState.INITIALIZED

    def start(self) -> None:
        """Bring the kernel to RUNNING, initializing registered services."""
        if self._state != LifecycleState.INITIALIZED:
            raise RuntimeError(f"start() requires INITIALIZED, got {self._state.name}")
        for name in self.container.names():
            svc = self.container.resolve(name)
            if hasattr(svc, "initialize"):
                svc.initialize()
            self._services[name] = svc
        self._state = LifecycleState.RUNNING

    def stop(self) -> None:
        """Halt the kernel."""
        if self._state != LifecycleState.RUNNING:
            raise RuntimeError(f"stop() called in {self._state.name}")
        self._services.clear()
        self._state = LifecycleState.STOPPED

    def service(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(name)
        return self._services[name]
