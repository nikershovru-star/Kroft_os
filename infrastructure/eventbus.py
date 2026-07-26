"""In-memory asynchronous event bus with optional JSONL persistence.

Implements contracts.IEventBus. Handlers may be sync or async; exceptions
in one handler are isolated and do not break others. An in-memory log is
kept for history. Optionally, every published event is appended to a
human-readable JSONL file via an injected contracts.IFileSystem store
(append-only, daily files under base_path/<topic>/<YYYY-MM-DD>.jsonl).
"""
from __future__ import annotations
import asyncio
import json
import shutil
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from contracts import IEventBus, IFileSystem


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryEventBus(IEventBus):
    def __init__(
        self,
        clock: Callable[[], Any] = _default_clock,
        store: Optional[IFileSystem] = None,
        base_path: str = "events",
    ) -> None:
        if store is not None and not isinstance(store, IFileSystem):
            raise TypeError("store must implement contracts.IFileSystem or be None")
        self._clock = clock
        self._store = store
        self._base_path = base_path
        self._handlers: Dict[str, List[Callable]] = {}
        self._history: List[Dict[str, Any]] = []
        self._running = False

    def subscribe(self, topic: str, handler: Callable) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, event: dict) -> None:
        stamped = dict(event)
        stamped["timestamp"] = self._now_iso()
        self._history.append({"topic": topic, **stamped})
        self._persist(topic, stamped)
        for handler in list(self._handlers.get(topic, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(stamped)
                else:
                    await asyncio.to_thread(handler, stamped)
            except Exception as exc:
                print(f"[InMemoryEventBus] handler error on '{topic}': {exc!r}")

    def publish_sync(self, topic: str, event: dict) -> None:
        stamped = dict(event)
        stamped["timestamp"] = self._now_iso()
        self._history.append({"topic": topic, **stamped})
        self._persist(topic, stamped)
        for handler in list(self._handlers.get(topic, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    self._run_coro(handler, stamped)
                else:
                    handler(stamped)
            except Exception as exc:
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

    def _now_iso(self) -> str:
        c = self._clock()
        if isinstance(c, datetime):
            return c.isoformat()
        return datetime.fromtimestamp(c, tz=timezone.utc).isoformat()

    def _persist(self, topic: str, stamped: dict) -> None:
        if self._store is None:
            return
        ts = stamped.get("timestamp") or ""
        date = ts[:10] if isinstance(ts, str) and len(ts) >= 10 else "unknown"
        path = f"{self._base_path}/{topic}/{date}.jsonl"
        line = json.dumps(
            {"t": ts, "topic": topic, "event": stamped}, ensure_ascii=False
        )
        self._store.append(path, line + "\n")

    def _read_disk(self, topic: str) -> List[Dict[str, Any]]:
        if self._store is None:
            return []
        dir_path = f"{self._base_path}/{topic}"
        try:
            files = self._store.list_dir(dir_path)
        except Exception:
            return []
        events: List[Dict[str, Any]] = []
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            try:
                # name is already relative to the store base (incl. base_path/topic/)
                content = self._store.read_content(name)
            except Exception:
                continue
            for raw in content.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                evt = rec.get("event", {})
                events.append(
                    {"topic": rec.get("topic", topic), "timestamp": rec.get("t"), **evt}
                )
        return events

    def get_history(self, topic: Optional[str] = None) -> List[dict]:
        if self._store is None or topic is None:
            if topic is None:
                return [dict(e) for e in self._history]
            return [dict(e) for e in self._history if e.get("topic") == topic]
        disk = self._read_disk(topic)
        merged: Dict[Any, dict] = {}
        for e in disk:
            merged[(e.get("topic"), e.get("timestamp"))] = e
        for e in self._history:
            if e.get("topic") == topic:
                merged.setdefault((e.get("topic"), e.get("timestamp")), e)
        return sorted(merged.values(), key=lambda x: x.get("timestamp") or "")

    def clear_history(self) -> None:
        self._history.clear()
        if self._store is not None:
            try:
                self._store.delete(self._base_path)
            except Exception:
                pass

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False
