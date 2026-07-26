"""Stage 27 - Watch Mode tests (8).

Tests the polling FileWatcher (the always-available fallback) + WatchService
trigger wiring. watchdog is not installed in this environment, so the watchdog
branch is exercised only as far as its fallback (polling) -- that is the honest
guaranteed path. WatchService.trigger() is verified with both a real async
crawler and a sync fake crawler (thread-safe loop path).
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Make the project importable when run directly.
ROOT = r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KnowledgeOS-v5"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from adapters.file_watcher import FileWatcher
from services.watch_service import WatchService


@pytest.fixture
def vault():
    d = tempfile.mkdtemp(prefix="hermes-watch-")
    Path(d).joinpath("A.md").write_text("alpha", encoding="utf-8")
    Path(d).joinpath("B.md").write_text("beta", encoding="utf-8")
    yield d
    # cleanup handled by OS tmp; best-effort removal.
    for f in ("A.md", "B.md", "C.md"):
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass


def test_watcher_polling_detects_new_file(vault):
    """Polling watcher fires callback when a new .md appears."""
    fired = []
    w = FileWatcher(vault, interval=0.1, use_watchdog=False)
    w.start(lambda: fired.append(1))
    try:
        # Give the poll loop one tick to snapshot.
        time.sleep(0.25)
        Path(vault).joinpath("C.md").write_text("gamma", encoding="utf-8")
        # Wait for a poll cycle after the change.
        deadline = time.time() + 3.0
        while not fired and time.time() < deadline:
            time.sleep(0.05)
    finally:
        w.stop()
    assert fired, "polling watcher did not detect the new .md file"


def test_watcher_polling_detects_edit(vault):
    """Polling watcher fires when an existing .md is modified (mtime change)."""
    fired = []
    w = FileWatcher(vault, interval=0.1, use_watchdog=False)
    w.start(lambda: fired.append(1))
    try:
        time.sleep(0.25)
        # Force a real mtime change (sleep + rewrite guarantees stat differs).
        time.sleep(0.05)
        Path(vault).joinpath("A.md").write_text("alpha EDITED", encoding="utf-8")
        deadline = time.time() + 3.0
        while len(fired) == 0 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        w.stop()
    assert fired, "polling watcher did not detect the file edit"


def test_watcher_stop_is_idempotent(vault):
    """stop() twice must not raise and is_running() reflects state."""
    w = FileWatcher(vault, interval=0.2, use_watchdog=False)
    w.start(lambda: None)
    assert w.is_running()
    w.stop()
    assert not w.is_running()
    w.stop()  # second stop must be safe
    assert not w.is_running()


def test_watcher_uses_polling_when_watchdog_missing(vault):
    """"using_watchdog" is False on this box (watchdog not installed)."""
    w = FileWatcher(vault, interval=0.2, use_watchdog=True)
    assert w._have_watchdog is False
    assert w.using_watchdog is False


# ----- WatchService -----

class _SyncCrawler:
    """Fake crawler with a SYNC crawl() (tests the non-coroutine branch)."""
    def __init__(self):
        self.calls = 0
    def crawl(self):
        self.calls += 1
        return {"files_scanned": self.calls, "nodes": self.calls}


class _AsyncCrawler:
    """Fake crawler with an ASYNC crawl() (tests the fresh-loop branch)."""
    def __init__(self):
        self.calls = 0
    async def crawl(self):
        self.calls += 1
        return {"files_scanned": self.calls, "nodes": self.calls * 2}


def test_watch_service_trigger_async_crawler():
    """trigger() runs an async crawler in a fresh loop and returns stats."""
    crawler = _AsyncCrawler()
    ws = WatchService(crawler, FileWatcher("x", use_watchdog=False))
    stats = ws.trigger()
    assert crawler.calls == 1
    assert stats == {"files_scanned": 1, "nodes": 2}
    assert ws.get_last_stats() == stats


def test_watch_service_trigger_sync_crawler():
    """trigger() handles a sync (non-coroutine) crawler too."""
    crawler = _SyncCrawler()
    ws = WatchService(crawler, FileWatcher("x", use_watchdog=False))
    stats = ws.trigger()
    assert crawler.calls == 1
    assert stats == {"files_scanned": 1, "nodes": 1}


def test_watch_service_trigger_swallows_crawl_error():
    """A broken crawl never propagates out of trigger()."""
    class _Broken:
        def crawl(self):
            raise RuntimeError("boom")
    ws = WatchService(_Broken(), FileWatcher("x", use_watchdog=False))
    # Must not raise.
    stats = ws.trigger()
    assert stats == {}


def test_watch_service_starts_watcher_and_triggers_on_change(vault):
    """start() wires the callback; a real file change drives a crawl."""
    crawler = _AsyncCrawler()
    w = FileWatcher(vault, interval=0.1, use_watchdog=False)
    ws = WatchService(crawler, w)
    ws.start()
    try:
        time.sleep(0.25)
        Path(vault).joinpath("C.md").write_text("gamma", encoding="utf-8")
        deadline = time.time() + 4.0
        while crawler.calls == 0 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        ws.stop()
    assert crawler.calls >= 1, "watcher change did not trigger a crawl"
