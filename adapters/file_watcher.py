"""File watcher adapter (Stage 27).

The ONLY place that touches the OS filesystem-notification surface. Two
backends, both optional-dependency-safe:

  * watchdog (if installed) -- event-driven, near-instant notification, runs
    its own background thread. Tried FIRST when ``use_watchdog=True``.
  * polling fallback (always available) -- ``os.walk`` + ``os.stat`` every
    ``interval`` seconds on a daemon thread. This is the guaranteed path when
    watchdog is not installed (the default on this project's CI/Windows box).

The watcher is duck-typed against a ``callback: Callable[[], None]`` -- it does
NOT know about crawlers or the kernel. ``WatchService`` (services/) wires the
callback to ``crawler.crawl()``.

Architecture contract: adapters/ may import contracts + stdlib. threading/time/
os are stdlib; no third-party import at module load (watchdog is imported lazily
inside a try/except so the module imports cleanly without it).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Dict, Optional

from contracts import IService


class FileWatcher:
    """Watch a vault directory for ``.md`` changes and fire ``callback``.

    Polling fallback is always available; watchdog is a bonus used only when
    installed AND ``use_watchdog=True``.
    """

    def __init__(
        self,
        vault_path: str,
        interval: float = 2.0,
        use_watchdog: bool = True,
    ) -> None:
        self._vault = vault_path
        self._interval = max(0.05, float(interval))
        self._use_watchdog = use_watchdog
        self._running = False
        self._callback: Optional[Callable[[], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._observer = None
        self._have_watchdog = self._try_import_watchdog()
        self._last: Dict[str, float] = {}

    # ----- watchdog (optional) -----
    def _try_import_watchdog(self) -> bool:
        if not self._use_watchdog:
            return False
        try:
            from watchdog.events import FileSystemEventHandler  # noqa: F401
            from watchdog.observers import Observer  # noqa: F401
            self._Observer = Observer
            self._Handler = FileSystemEventHandler
            return True
        except ImportError:
            return False

    # ----- mtime snapshot (polling) -----
    def _snapshot(self) -> Dict[str, float]:
        snap: Dict[str, float] = {}
        for root, _dirs, files in os.walk(self._vault):
            for f in files:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(root, f)
                try:
                    snap[os.path.relpath(p, self._vault)] = os.stat(p).st_mtime
                except OSError:
                    pass
        return snap

    def _on_watchdog_event(self, event) -> None:
        # Skip directory events; react to any file change.
        if getattr(event, "is_directory", False):
            return
        if self._callback is not None:
            self._callback()

    def _poll_loop(self) -> None:
        self._last = self._snapshot()
        while self._running:
            time.sleep(self._interval)
            if not self._running:
                break
            cur = self._snapshot()
            if cur != self._last:
                self._last = cur
                if self._callback is not None:
                    self._callback()

    # ----- lifecycle -----
    def start(self, callback: Callable[[], None]) -> None:
        """Begin watching; invoke ``callback`` whenever a ``.md`` changes."""
        if self._running:
            return
        self._callback = callback
        self._running = True
        if self._have_watchdog:
            try:
                handler = self._Handler()
                handler.on_any_event = self._on_watchdog_event
                self._observer = self._Observer()
                self._observer.schedule(handler, self._vault, recursive=True)
                self._observer.start()
                return
            except Exception:
                # Any watchdog failure -> fall back to polling.
                self._observer = None
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._callback = None

    def is_running(self) -> bool:
        return self._running

    @property
    def using_watchdog(self) -> bool:
        """True only if the watchdog observer is actually live (bonus path)."""
        return self._observer is not None
