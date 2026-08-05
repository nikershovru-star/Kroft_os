"""Stage 14 - Periodic Autosave & Watchdog tests (6).

The watchdog runs a dedicated asyncio loop on a daemon thread. To test it
without real wall-clock waiting, Kernel accepts an injectable `sleep_fn`
(async) and `clock`. We drive ticks by firing a controllable asyncio.Event
inside the watchdog's own loop (a helper that schedules the set on the loop).
"""
import asyncio
import tempfile
from datetime import datetime, timezone
from unittest import mock

import pytest

from kernel import Kernel, LifecycleState
from infrastructure import DependencyContainer, InMemoryGraphBuilder, InMemoryEventBus
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter


def _build_container(tmp=None):
    if tmp is None:
        tmp = tempfile.mkdtemp()
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(tmp))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    return c, tmp


class _ControllableSleep:
    """Async sleep that blocks until `tick()` is called from the test."""

    def __init__(self):
        self._event = asyncio.Event()
        self._scheduled = []

    async def __call__(self, sec):
        # Wait until the test fires the latch.
        await self._event.wait()
        self._event.clear()

    def tick(self, loop):
        """Fire the latch from the test thread (schedule on watchdog loop)."""
        loop.call_soon_threadsafe(self._event.set)


def _make_kernel(interval=1.0, sleep=None, clock=None, tmp=None):
    c, tmp = _build_container(tmp)
    slp = sleep if sleep is not None else _ControllableSleep()
    k = Kernel(
        c,
        autosave_interval_sec=interval,
        sleep_fn=slp,
        clock=clock if clock is not None else (lambda: datetime.now(timezone.utc)),
    )
    return k, c, slp


def _awake(kernel, sleeps, n=1):
    """Drive the watchdog coroutine `n` ticks and let it complete."""
    loop = kernel._autosave_event_loop
    for _ in range(n):
        sleeps.tick(loop)
        # Give the watchdog loop time to resume + snapshot + emit.
        import time
        time.sleep(0.15)


def test_autosave_emits_event():
    k, c, slp = _make_kernel()
    k.initialize()
    k.start()
    assert k._autosave_task is not None
    _awake(k, slp, n=1)
    hist = c.resolve("IEventBus").get_history("GraphAutosaved")
    assert len(hist) >= 1, "GraphAutosaved not emitted"
    assert "timestamp" in hist[-1]
    k.stop()


def test_autosave_calls_snapshot():
    k, c, slp = _make_kernel()
    k.initialize()
    k.start()
    with mock.patch.object(k, "_try_snapshot_graph", wraps=k._try_snapshot_graph) as spy:
        _awake(k, slp, n=1)
        # Wait a hair more for the call to land.
        import time
        time.sleep(0.1)
        assert spy.called, "_try_snapshot_graph was not called by the watchdog"
    k.stop()


def test_autosave_disabled_by_default():
    # autosave_interval_sec=None (default) -> no watchdog task.
    c, tmp = _build_container()
    k = Kernel(c)  # default: autosave off
    k.initialize()
    k.start()
    assert k._autosave_task is None, "watchdog must not run when disabled"
    k.stop()


def test_stop_cancels_autosave():
    k, c, slp = _make_kernel()
    k.initialize()
    k.start()
    assert k._autosave_task is not None
    k.stop()
    assert k._autosave_task is None, "autosave task must be cancelled on stop"
    assert k.state == LifecycleState.STOPPED


def test_atexit_registration(monkeypatch):
    # main.build_container + cmd_crawl register an atexit hook that calls k.stop().
    import main
    import atexit

    captured = []
    monkeypatch.setattr(atexit, "register", lambda fn, *a, **kw: captured.append(fn))

    c, tmp = _build_container()
    k = main.build_container(tmp)
    args = type("A", (), {"vault": tmp, "autosave": 0})()
    # Import lazily to avoid top-level atexit side effects at import time.
    from cli import commands
    commands.cmd_crawl(args, k)

    assert captured, "atexit.register was not called"
    # The registered callable should be a zero-arg stop wrapper.
    hook = captured[-1]
    # It must not raise when invoked (kernel is RUNNING -> STOPPED).
    hook()
    assert k.resolve("IGraphBuilder") is not None


def test_autosave_no_graph_noop():
    # autosave configured but IGraphBuilder NOT wired -> no crash, no task.
    c = DependencyContainer()
    tmp = tempfile.mkdtemp()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(tmp))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    # NOTE: IGraphBuilder intentionally omitted.
    k = Kernel(c, autosave_interval_sec=1.0, sleep_fn=_ControllableSleep())
    k.initialize()
    k.start()
    assert k._autosave_task is None, "no watchdog without IGraphBuilder wired"
    k.stop()  # must not raise
    assert k.state == LifecycleState.STOPPED
