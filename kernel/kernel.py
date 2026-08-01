"""KROFT_OS v5 Kernel — lifecycle orchestrator (Phase B.2/B.3/B.4 refactored).

Kernel is PURE (ADR-028): it imports ONLY contracts + runtime + stdlib.
It NO LONGER imports infrastructure (DependencyContainer / SnapshotStore).

Dependency injection (constructor):
  Kernel(runtime_context, event_bus, state_repository, registry, services=None)
Container-aware factory (Composition Root only):
  Kernel(container)  -- accepts a fully-built DependencyContainer, resolves
  capabilities from it. K3-compliant: kernel never instantiates the container
  class (composition/ does); the container arrives already-wired. Kept as the
  canonical assembly path used by composition/build_kernel and the test-suite seam.
Kernel creates NOTHING — every dependency arrives fully-built via the
Composition Root (composition/).

constructor injection.

Stage 14: background autosave watchdog (injectable sleep_fn/clock).
"""
from __future__ import annotations
import asyncio
import threading
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

from contracts import (
    ISnapshotable, ICapabilityRegistry, IEventBus, IFileSystem, IGraphBuilder,
    IKernel, IStateRepository,
)
from runtime import RuntimeContext


class LifecycleState(Enum):
    UNINITIALIZED = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    FAILED = auto()
    STOPPED = auto()


class Kernel(IKernel):
    """Microkernel: lifecycle state machine + orchestration ONLY through ports.

    Implements contracts.IKernel (ADR-020 variant b): the Runtime Host depends
    only on the IKernel port. No second kernel. No infrastructure import (K1).
    """

    def __init__(
        self,
        # ---- legacy / deprecated positional: DI container (backward-compat) ----
        container: Optional[Any] = None,
        # ---- Phase B.2: explicit constructor injection (preferred) ----
        runtime_context: Optional[RuntimeContext] = None,
        event_bus: Optional[IEventBus] = None,
        state_repository: Optional[IStateRepository] = None,
        registry: Optional[ICapabilityRegistry] = None,
        services: Optional[Dict[str, Any]] = None,
        autosave_interval_sec: Optional[float] = None,
        sleep_fn: Optional[Callable[[float], Any]] = None,
        clock: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.container = container  # deprecated; kept for backward-compat tests
        self._state = LifecycleState.UNINITIALIZED
        self._services: Dict[str, Any] = dict(services) if services else {}
        self.runtime_context: Optional[RuntimeContext] = runtime_context
        # Core capabilities — injected, NOT resolved from container by default.
        self.wired: Dict[str, Any] = {}
        if registry is not None:
            self.wired["ICapabilityRegistry"] = registry
        if event_bus is not None:
            self.wired["IEventBus"] = event_bus
        self._event_bus: Optional[IEventBus] = event_bus
        # Phase B.3: state persistence via IStateRepository port (no SnapshotStore).
        self._state_repository: Optional[IStateRepository] = state_repository
        self._autosave_interval_sec = autosave_interval_sec
        self._sleep = sleep_fn if sleep_fn is not None else asyncio.sleep
        self._clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))
        self._autosave_task: Optional["asyncio.Task[None]"] = None
        self._autosave_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._autosave_thread: Optional[threading.Thread] = None

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def event_bus(self) -> Optional[IEventBus]:
        return self._event_bus

    def initialize(self) -> None:
        """Wire injected capabilities and recover persisted state."""
        if self._state != LifecycleState.UNINITIALIZED:
            raise RuntimeError(f"initialize() called in {self._state.name}")
        if self.runtime_context is None:
            self.runtime_context = RuntimeContext()
        # Legacy path: resolve optional caps from container if no explicit ones.
        if self.container is not None:
            for cap_name in ("ICapabilityRegistry", "IFileSystem", "IEventBus", "IGraphBuilder", "IStateRepository"):
                if cap_name not in self.wired and self.container.has(cap_name):
                    self.wired[cap_name] = self.container.resolve(cap_name)
        if "IStateRepository" in self.wired and self._state_repository is None:
            self._state_repository = self.wired["IStateRepository"]
        if "ICapabilityRegistry" in self.wired:
            self.runtime_context.capabilities = self.wired["ICapabilityRegistry"]
        if self._event_bus is None:
            self._event_bus = self.wired.get("IEventBus")
        if self._event_bus is not None:
            self._event_bus.start()
        # Phase B.3: recover graph + index via IStateRepository (no SnapshotStore).
        self._try_restore_graph()
        self._try_restore_index()
        self._state = LifecycleState.INITIALIZED

    # ----- Stage 19: index persistence helpers (via IStateRepository) -----
    def _index_snapshot_path(self) -> str:
        return "data/index_snapshot.json"

    def _try_restore_index(self) -> None:
        """Best-effort ContentIndex + SemanticIndex recovery on initialize()."""
        repo = self._state_repository
        if repo is None:
            return
        data = repo.load_snapshot()
        if data is None or "index" not in data:
            return
        index = self._resolve_snapshotable("ContentIndex")
        if index is not None:
            try:
                index.restore(data["index"])
                self.emit("IndexRestored", {"path": self._index_snapshot_path()})
            except Exception:
                pass
        sem = self._resolve_snapshotable("SemanticIndex")
        if sem is not None and "semantic" in data:
            try:
                sem.restore(data["semantic"])
                self.emit("SemanticRestored", {"path": self._index_snapshot_path()})
            except Exception:
                pass

    def _resolve_snapshotable(self, key: str):
        """Return a registered service that implements ISnapshotable, else None."""
        if self.container is not None and self.container.has(key):
            svc = self.container.resolve(key)
            if isinstance(svc, ISnapshotable):
                return svc
        return self._services.get(key) if isinstance(self._services.get(key), ISnapshotable) else None

    def _try_snapshot_index(self) -> None:
        """Best-effort Index + SemanticIndex persistence (composite snapshot)."""
        repo = self._state_repository
        if repo is None:
            return
        index = self._resolve_snapshotable("ContentIndex")
        if index is None:
            return
        payload: Dict[str, Any] = {"version": 2, "index": index.snapshot()}
        sem = self._resolve_snapshotable("SemanticIndex")
        if sem is not None:
            payload["semantic"] = sem.snapshot()
        try:
            repo.save_snapshot(payload)
            self.emit("IndexSnapshotted", {"path": self._index_snapshot_path()})
            if sem is not None:
                self.emit("SemanticSnapshotted", {"path": self._index_snapshot_path()})
        except Exception:
            pass

    # ----- Stage 12: graph persistence helpers (via IGraphBuilder + repo) -----
    def _graph_snapshot_path(self) -> str:
        return "data/graph_snapshot.json"

    def _try_restore_graph(self) -> None:
        """Best-effort graph recovery on initialize()."""
        graph = self.wired.get("IGraphBuilder")
        fs = self.wired.get("IFileSystem")
        if graph is None or fs is None:
            return
        try:
            ok = graph.restore(fs, self._graph_snapshot_path())
        except Exception:
            ok = False
        if ok:
            self.emit("GraphRestored", {"path": self._graph_snapshot_path()})

    def _try_snapshot_graph(self) -> None:
        """Best-effort graph persistence on stop()/autosave."""
        graph = self.wired.get("IGraphBuilder")
        fs = self.wired.get("IFileSystem")
        if graph is None or fs is None:
            return
        try:
            graph.snapshot(fs, self._graph_snapshot_path())
            self.emit("GraphSnapshotted", {"path": self._graph_snapshot_path()})
        except Exception:
            pass
        self._try_snapshot_index()

    def start(self) -> None:
        """Bring the kernel to RUNNING, initializing registered services."""
        if self._state != LifecycleState.INITIALIZED:
            raise RuntimeError(f"start() requires INITIALIZED, got {self._state.name}")
        self.emit("kernel.lifecycle", {"type": "kernel.started"})
        self._state = LifecycleState.RUNNING
        self._start_autosave()

    def stop(self) -> None:
        """Halt the kernel. Idempotent."""
        if self._state == LifecycleState.STOPPED:
            return
        if self._state != LifecycleState.RUNNING:
            self._state = LifecycleState.STOPPED
            return
        self._stop_autosave()
        self._try_snapshot_graph()
        self.emit("kernel.lifecycle", {"type": "kernel.stopped"})
        self._services.clear()
        if self._event_bus is not None:
            self._event_bus.stop()
        self._state = LifecycleState.STOPPED

    def panic(self, reason: Optional[str] = None) -> None:
        """Level 3 emergency: snapshot, mark FAILED, emit panic, then stop."""
        if self._state == LifecycleState.STOPPED:
            return
        try:
            self._stop_autosave()
            self._try_snapshot_graph()
        except Exception:
            pass
        self._state = LifecycleState.FAILED
        self.emit("kernel.panic", {"reason": reason or "unknown"})
        try:
            self._services.clear()
            if self._event_bus is not None:
                self._event_bus.stop()
        except Exception:
            pass
        self._state = LifecycleState.STOPPED

    # ----- Stage 14: periodic autosave watchdog -----
    def _start_autosave(self) -> None:
        if self._autosave_interval_sec is None or self._autosave_interval_sec <= 0:
            return
        if self.wired.get("IGraphBuilder") is None or self.wired.get("IFileSystem") is None:
            return
        if self._autosave_task is not None:
            return
        self._autosave_event_loop = asyncio.new_event_loop()
        self._autosave_task = self._autosave_event_loop.create_task(self._autosave_loop())
        self._autosave_thread = threading.Thread(target=self._run_autosave_loop, daemon=True)
        self._autosave_thread.start()

    def _run_autosave_loop(self) -> None:
        loop = self._autosave_event_loop
        if loop is None:
            return
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _autosave_loop(self) -> None:
        interval = self._autosave_interval_sec
        while self._state == LifecycleState.RUNNING:
            try:
                await self._sleep(interval)
            except asyncio.CancelledError:
                break
            if self._state != LifecycleState.RUNNING:
                break
            self._try_snapshot_graph()
            self.emit("GraphAutosaved", {"timestamp": self._clock().isoformat()})

    def _stop_autosave(self) -> None:
        task = self._autosave_task
        loop = self._autosave_event_loop
        self._autosave_task = None
        if task is not None and loop is not None:
            loop.call_soon_threadsafe(task.cancel)
            loop.call_soon_threadsafe(loop.stop)
        if self._autosave_thread is not None:
            self._autosave_thread.join(timeout=2.0)
            self._autosave_thread = None

    def emit(self, topic: str, event: dict) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish_sync(topic, event)

    def save(self) -> None:
        """Force a graph snapshot while the kernel keeps running (Stage 16)."""
        self._try_snapshot_graph()

    def service(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(name)
        return self._services[name]
