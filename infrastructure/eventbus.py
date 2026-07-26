"""In-memory asynchronous event bus.

Implements contracts.IEventBus. Handlers may be sync or async; exceptions
in one handler are isolated and do not break others. An in-memory log is
kept for history. Persistence via an optional IFileSystem store is NOT
implemented in this stage (the store parameter is accepted for DI symmetry
only - see README HONEST LIMITATIONS).
"""
from __future__ import annotations
import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from contracts import IEventBus, IFileSystem


class InMemoryEventBus(IEventBus):
    def __init__(self, clock: Callable[[], float] = time.time, store: Optional[IFileSystem] = None) -> None:
        if store is not None and not isinstance(store, IFileSystem):
            raise TypeError("store must implement contracts.IFileSystem or be None")
        self._clock = clock
        self._store = store  # accepted for DI symmetry; persistence not implemented
        self._handlers: Dict[str, List[Callable]] = {}
        self._history: List[Dict[str, Any]] = []
        self._running = False

    # --- subscription ---
    def subscribe(self, topic: str, handler: Callable) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    # --- publishing (async) ---
    async def publish(self, topic: str, event: dict) -> None:
        stamped = dict(event)
        stamped.setdefault("timestamp", self._clock())
        self._history.append({"topic": topic, **stamped})
        self._maybe_persist(topic, stamped)
        for handler in list(self._handlers.get(topic, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(stamped)
                else:
                    await asyncio.to_thread(handler, stamped)
            except Exception as exc:  # error isolation
                print(f"[InMemoryEventBus] handler error on '{topic}': {exc!r}")

    # --- publishing (sync wrapper for legacy code) ---
    def publish_sync(self, topic: str, event: dict) -> None:
        stamped = dict(event)
        stamped.setdefault("timestamp", self._clock())
        self._history.append({"topic": topic, **stamped})
        self._maybe_persist(topic, stamped)
        for handler in list(self._handlers.get(topic, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    self._run_coro(handler, stamped)
                else:
                    handler(stamped)
            except Exception as exc:  # error isolation
                print(f"[InMemoryEventBus] handler error on '{topic}': {exc!r}")

    @staticmethod
    def _run_coro(coro_fn: Callable, event: dict) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            asyncio.run(coro_fn(event))
        else:
            fut = asyncio.run_coroutine_threadsafe(coro_fn(event), loop)
            fut.result()

    # --- history / query ---
    def get_history(self, topic: Optional[str] = None) -> List[dict]:
        if topic is None:
            return [dict(e) for e in self._history]
        return [dict(e) for e in self._history if e.get("topic") == topic]

    def clear_history(self) -> None:
        self._history.clear()

    # --- lifecycle (port required) ---
    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def _maybe_persist(self, topic: str, event: dict) -> None:
        # Persistence via IFileSystem is NOT implemented in this stage.
        # Documented limitation (see README HONEST LIMITATIONS).
        return None
