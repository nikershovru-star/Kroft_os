"""KROFT_OS v5 Kernel — lifecycle orchestrator.

The kernel owns a single DependencyContainer (the composition root) and
drives a strict lifecycle state machine. It does NOT import concrete
adapters; everything is resolved through the container (including the
event bus, referenced only via contracts.IEventBus).

Stage 14: a background autosave watchdog can be enabled via
`autosave_interval_sec`. While RUNNING, a dedicated daemon thread drives its
own asyncio event loop running `_autosave_loop()`, which snapshots the graph
every interval and emits `GraphAutosaved`. The timer is injectable (sleep_fn /
clock) so tests can drive ticks without real wall-clock waiting.
"""
from __future__ import annotations
import asyncio
import threading
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

from infrastructure import DependencyContainer
from infrastructure.snapshot_store import SnapshotStore
from contracts import ISnapshotable, ICapabilityRegistry, IEventBus, IFileSystem, IGraphBuilder, IKernel
from runtime import RuntimeContext


class LifecycleState(Enum):
    UNINITIALIZED = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    STOPPED = auto()


class Kernel(IKernel):
    """Microkernel: composition root + lifecycle state machine.

    Implements contracts.IKernel (ADR-020 variant b): the Runtime Host depends
    only on the IKernel port, never on this concrete class. No second kernel.
    """

    def __init__(
        self,
        container: Optional[DependencyContainer] = None,
        autosave_interval_sec: Optional[float] = None,
        sleep_fn: Optional[Callable[[float], Any]] = None,
        clock: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.container = container if container is not None else DependencyContainer()
        self._state = LifecycleState.UNINITIALIZED
        self._services: Dict[str, Any] = {}
        self.runtime_context: Optional[RuntimeContext] = None
        # Core capabilities resolved from the container during initialize().
        self.wired: Dict[str, Any] = {}
        self._event_bus: Optional[IEventBus] = None
        # Stage 19: composite snapshot store (graph restored in-place via
        # IGraphBuilder.restore; ContentIndex restores through ISnapshotable).
        self._snapshot_store: Optional["SnapshotStore"] = None
        # Stage 14: periodic autosave watchdog configuration.
        self._autosave_interval_sec = autosave_interval_sec
        self._sleep = sleep_fn if sleep_fn is not None else asyncio.sleep
        self._clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))
        self._autosave_task: Optional["asyncio.Task[None]"] = None
        self._autosave_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._autosave_thread: Optional[threading.Thread] = None

    @property
    def state(self) -> LifecycleState:
        return self._state

    def initialize(self) -> None:
        """Resolve core capabilities from the container and wire them in."""
        if self._state != LifecycleState.UNINITIALIZED:
            raise RuntimeError(f"initialize() called in {self._state.name}")
        self.runtime_context = RuntimeContext()
        # Resolve optional core capabilities if registered in the container.
        for cap_name in ("ICapabilityRegistry", "IFileSystem", "IEventBus", "IGraphBuilder"):
            if self.container.has(cap_name):
                self.wired[cap_name] = self.container.resolve(cap_name)
        if "ICapabilityRegistry" in self.wired:
            self.runtime_context.capabilities = self.wired["ICapabilityRegistry"]
        self._event_bus = self.wired.get("IEventBus")
        if self._event_bus is not None:
            self._event_bus.start()
        # Stage 19: composite snapshot store for ContentIndex (graph is
        # persisted separately by IGraphBuilder — see _try_snapshot_graph).
        fs = self.wired.get("IFileSystem")
        if fs is not None:
            self._snapshot_store = SnapshotStore(fs, self._index_snapshot_path())
        # Stage 12: attempt to recover the knowledge graph from persistent
        # storage so a kernel restart resumes where it stopped.
        self._try_restore_graph()
        # Stage 19: restore the in-memory ContentIndex from its own snapshot
        # so a fresh CLI/REPL process starts with a warm index (no re-crawl).
        self._try_restore_index()
        self._state = LifecycleState.INITIALIZED

    # ----- Stage 19: index persistence helpers -----
    def _index_snapshot_path(self) -> str:
        return "data/index_snapshot.json"

    def _try_restore_index(self) -> None:
        """Best-effort ContentIndex + SemanticIndex recovery on initialize().

        Both snapshotables live in ONE composite file (data/index_snapshot.json,
        {"version":2, "index":..., "semantic":...}) so a single atomic write
        (Stage 19) persists them together — a second save() would otherwise
        clobber the first. No-op if no store / no services / missing / corrupt.
        """
        store = self._snapshot_store
        if store is None:
            return
        data = store.load()
        if data is None or "index" not in data:
            return
        index = self._resolve_snapshotable("ContentIndex")
        if index is not None:
            try:
                index.restore(data["index"])
                self.emit("IndexRestored", {"path": self._index_snapshot_path()})
            except Exception:
                pass
        # Stage 29: semantic embeddings share the same composite file.
        sem = self._resolve_snapshotable("SemanticIndex")
        if sem is not None and "semantic" in data:
            try:
                sem.restore(data["semantic"])
                self.emit("SemanticRestored", {"path": self._index_snapshot_path()})
            except Exception:
                pass

    def _resolve_snapshotable(self, key: str):
        """Return a registered service that implements ISnapshotable, else None.

        Uses runtime_checkable typing.Protocol so we never import the concrete
        ContentIndex at the kernel layer (axis-clean: kernel depends only on
        contracts.ISnapshotable, not on services).
        """
        if not self.container.has(key):
            return None
        svc = self.container.resolve(key)
        if isinstance(svc, ISnapshotable):
            return svc
        return None

    def _try_snapshot_index(self) -> None:
        """Best-effort Index + SemanticIndex persistence (composite snapshot).

        Stage 19 persists the ContentIndex; Stage 29 adds the SemanticIndex to
        the SAME atomic file ({"version":2, "index":..., "semantic":...}) so a
        single SnapshotStore.save() writes both. Emits IndexSnapshotted /
        SemanticSnapshotted. No-op if unwired; silent on write failure.
        """
        store = self._snapshot_store
        if store is None:
            return
        index = self._resolve_snapshotable("ContentIndex")
        if index is None:
            return
        payload: Dict[str, Any] = {"version": 2, "index": index.snapshot()}
        sem = self._resolve_snapshotable("SemanticIndex")
        if sem is not None:
            payload["semantic"] = sem.snapshot()
        try:
            store.save(payload)
            self.emit("IndexSnapshotted", {"path": self._index_snapshot_path()})
            if sem is not None:
                self.emit("SemanticSnapshotted", {"path": self._index_snapshot_path()})
        except Exception:
            pass

    # ----- Stage 12: graph persistence helpers -----
    def _graph_snapshot_path(self) -> str:
        return "data/graph_snapshot.json"

    def _try_restore_graph(self) -> None:
        """Best-effort graph recovery on initialize().

        Only runs if both IGraphBuilder and IFileSystem are wired. Emits a
        GraphRestored event (via IEventBus) when the restore succeeded; emits
        nothing on a fresh/no-prior-snapshot start (silent no-op).
        """
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
        """Best-effort graph persistence on stop()/autosave.

        Emits GraphSnapshotted via IEventBus. No-op if graph/fs unwired.
        On write failure the snapshot is silently skipped (no backoff, no retry).
        """
        graph = self.wired.get("IGraphBuilder")
        fs = self.wired.get("IFileSystem")
        if graph is None or fs is None:
            return
        try:
            graph.snapshot(fs, self._graph_snapshot_path())
            self.emit("GraphSnapshotted", {"path": self._graph_snapshot_path()})
        except Exception:
            pass
        # Stage 19: persist the ContentIndex alongside the graph.
        self._try_snapshot_index()

    def start(self) -> None:
        """Bring the kernel to RUNNING, initializing registered services."""
        if self._state != LifecycleState.INITIALIZED:
            raise RuntimeError(f"start() requires INITIALIZED, got {self._state.name}")
        for name in self.container.names():
            svc = self.container.resolve(name)
            if hasattr(svc, "initialize"):
                svc.initialize()
            self._services[name] = svc
        self.emit("kernel.lifecycle", {"type": "kernel.started"})
        self._state = LifecycleState.RUNNING
        # Stage 14: launch the background autosave watchdog (no-op unless configured).
        self._start_autosave()

    def stop(self) -> None:
        """Halt the kernel.

        Idempotent: calling stop() again (e.g. an atexit hook firing after an
        explicit stop(), or on an UNINITIALIZED kernel) is a safe no-op. This
        is required for the Stage 14 atexit guarantee — a graceful exit must
        not raise if the command already tore the kernel down.
        """
        if self._state == LifecycleState.STOPPED:
            return
        if self._state != LifecycleState.RUNNING:
            # UNINITIALIZED/INITIALIZED: nothing was started; nothing to stop.
            self._state = LifecycleState.STOPPED
            return
        # Stage 14: cancel the autosave watchdog first so it does not race with
        # (or outlive) the final shutdown snapshot.
        self._stop_autosave()
        # Stage 12: persist the knowledge graph before halting.
        self._try_snapshot_graph()
        self.emit("kernel.lifecycle", {"type": "kernel.stopped"})
        self._services.clear()
        if self._event_bus is not None:
            self._event_bus.stop()
        self._state = LifecycleState.STOPPED

    # ----- Stage 14: periodic autosave watchdog -----
    def _start_autosave(self) -> None:
        """Launch the background autosave timer (no-op unless configured).

        Only runs when autosave_interval_sec > 0 AND both IGraphBuilder and
        IFileSystem are wired (persistence requires both). Runs a dedicated
        asyncio event loop on a daemon thread so the watchdog keeps ticking
        while the synchronous CLI command continues.
        """
        if self._autosave_interval_sec is None or self._autosave_interval_sec <= 0:
            return
        if self.wired.get("IGraphBuilder") is None or self.wired.get("IFileSystem") is None:
            return
        if self._autosave_task is not None:
            return
        self._autosave_event_loop = asyncio.new_event_loop()
        self._autosave_task = self._autosave_event_loop.create_task(self._autosave_loop())
        self._autosave_thread = threading.Thread(
            target=self._run_autosave_loop, daemon=True
        )
        self._autosave_thread.start()

    def _run_autosave_loop(self) -> None:
        """Target for the watchdog daemon thread: drive its own event loop."""
        loop = self._autosave_event_loop
        if loop is None:
            return
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _autosave_loop(self) -> None:
        """Background coroutine: snapshot the graph every interval while RUNNING.

        Uses an injectable sleep (self._sleep) so tests can drive ticks without
        real wall-clock waiting, and an injectable clock (self._clock) for the
        GraphAutosaved timestamp. Cancellation at shutdown breaks the loop.
        """
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
        """Cancel the watchdog task and stop its thread/loop (best effort)."""
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
        """Proxy to the wired event bus. No-op if no bus registered."""
        if self._event_bus is None:
            return
        self._event_bus.publish_sync(topic, event)

    def save(self) -> None:
        """Force a graph snapshot while the kernel keeps running (Stage 16).

        Public, side-effect-light wrapper around the existing best-effort
        persist helper used by ``stop()``. Emits ``GraphSnapshotted`` on
        success, silent no-op when graph/fs are not wired or on write failure.
        Safe to call repeatedly; does NOT change the lifecycle state, so the
        REPL can keep serving commands after a save.
        """
        self._try_snapshot_graph()

    def service(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(name)
        return self._services[name]
