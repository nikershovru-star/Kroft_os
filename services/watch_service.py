"""Watch Service (Stage 27) -- application-layer IService.

Wires a ``FileWatcher`` (adapters/) callback to a ``VaultStreamCrawler``
re-crawl. The watcher and crawler are INJECTED (duck-typed) -- this module
imports ONLY ``contracts`` + stdlib, never adapters/infrastructure, preserving
the arch gate.

Collision handled: ``VaultStreamCrawler.crawl()`` is a coroutine. The watcher
may fire from a background thread (polling daemon thread, or watchdog's own
thread), where no event loop is running. So ``trigger()`` runs the crawl in a
FRESH event loop (``asyncio.new_event_loop``) -- thread-safe and loop-isolated,
unlike ``asyncio.run`` which binds to the calling thread's context.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from contracts import IService


class WatchService(IService):
    """Trigger ``crawler.crawl()`` whenever the watched vault changes."""

    def __init__(
        self,
        crawler: Any,
        watcher: Any,
        kernel: Any = None,
        interval: float = 2.0,
        use_watchdog: bool = True,
    ) -> None:
        self._crawler = crawler          # duck-typed VaultStreamCrawler
        self._watcher = watcher          # duck-typed FileWatcher
        # Optional Kernel reference (duck-typed -- NOT an import of kernel,
        # preserving the arch gate). After each crawl we persist a snapshot so
        # a crash between watches loses at most one interval of changes.
        self._kernel = kernel
        self._interval = interval
        self._use_watchdog = use_watchdog
        self._last_stats: Dict[str, Any] = {}

    # ----- IService -----
    def name(self) -> str:
        return "watch_service"

    def initialize(self, context: Any | None = None) -> None:
        return None

    def execute(self, context_data: dict) -> str | list[str]:
        # Long-running: block until stopped, then report.
        self.watch()
        return "watch stopped"

    # ----- crawl driver (thread-safe) -----
    def _run_crawl(self) -> Dict[str, Any]:
        coro = self._crawler.crawl()
        if not asyncio.iscoroutine(coro):
            # Test fakes / non-async crawlers: return as-is.
            return coro if coro is not None else {}
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def trigger(self) -> Dict[str, Any]:
        """Run a crawl now (also the callback the watcher invokes).

        Returns the crawler stats dict; on any failure returns ``{}`` so a bad
        crawl never kills the watch loop. After a successful crawl, persists a
        graph snapshot via the injected Kernel (if any) so changes survive a
        crash between watches.
        """
        try:
            stats = self._run_crawl()
        except Exception:
            stats = {}
        if stats is None:
            stats = {}
        self._last_stats = stats
        if stats and self._kernel is not None:
            try:
                self._kernel.save()
            except Exception:
                pass
        return stats

    # ----- lifecycle -----
    def start(self) -> None:
        self._watcher.start(self.trigger)

    def stop(self) -> None:
        self._watcher.stop()

    def watch(self) -> None:
        """Blocking loop: watch until KeyboardInterrupt / stop()."""
        self.start()
        try:
            while self._watcher.is_running():
                time.sleep(0.2)
        except (KeyboardInterrupt, Exception):
            pass
        finally:
            self.stop()

    def get_last_stats(self) -> Dict[str, Any]:
        return dict(self._last_stats)
