"""Stage 17 - Incremental Crawl tests (8).

CrawlStateTracker (services/incremental_tracker.py) + differential crawl in
VaultStreamCrawler. Real tmp vaults + LocalFileSystemAdapter; mtime changes
are forced with os.utime (coarse filesystem mtime resolution would otherwise
make "modified" undetectable within a fast test).

Gate mapping:
  Incremental  -> test_crawl_up_to_date
  Regression   -> test_zero_regression_without_tracker
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from adapters import LocalFileSystemAdapter
from infrastructure import InMemoryGraphBuilder, InMemoryEventBus
from services import VaultStreamCrawler, CrawlStateTracker


def _make_vault(tmp_path: Path) -> str:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text("hub [[B.md]] [[C.md]]", encoding="utf-8")
    (vault / "B.md").write_text("leaf #todo", encoding="utf-8")
    (vault / "C.md").write_text("leaf #idea", encoding="utf-8")
    return str(vault)


def _bump_mtime(path: str, offset: float = 10.0) -> None:
    """Force a DIFFERENT mtime regardless of filesystem timestamp resolution."""
    t = time.time() + offset
    os.utime(path, (t, t))


def _crawler(vault: str, tracker=None):
    fs = LocalFileSystemAdapter(vault)
    graph = InMemoryGraphBuilder()
    if tracker is None:
        tracker_obj = None
    elif tracker is True:
        tracker_obj = CrawlStateTracker(fs)
    else:
        tracker_obj = tracker
    crawler = VaultStreamCrawler(
        fs, InMemoryEventBus(), graph, vault, tracker=tracker_obj
    )
    return crawler, graph, fs, tracker_obj


# --------------------------------------------------------------------------
def test_tracker_loads_empty_state(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    tracker = CrawlStateTracker(fs)
    # No .crawl_state.json on disk -> {} (never raises).
    assert tracker.load_state() == {}
    # Corrupt JSON -> {} too (never raises).
    fs.write_content(".crawl_state.json", "{not valid json!!!")
    assert tracker.load_state() == {}


def test_tracker_detects_new_file(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    tracker = CrawlStateTracker(fs)
    tracker.save_state(tracker.scan_mtimes(vault))  # baseline: 3 files known
    (Path(vault) / "D.md").write_text("new note", encoding="utf-8")
    changed, deleted = tracker.get_changed_files(vault)
    assert "D.md" in changed
    assert deleted == []
    # Pre-existing unchanged files are NOT reported.
    assert "A.md" not in changed


def test_tracker_detects_modified_file(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    tracker = CrawlStateTracker(fs)
    tracker.save_state(tracker.scan_mtimes(vault))
    b = os.path.join(vault, "B.md")
    Path(b).write_text("leaf #done edited", encoding="utf-8")
    _bump_mtime(b)
    changed, deleted = tracker.get_changed_files(vault)
    assert changed == ["B.md"]
    assert deleted == []


def test_tracker_detects_deleted_file(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    tracker = CrawlStateTracker(fs)
    tracker.save_state(tracker.scan_mtimes(vault))
    os.remove(os.path.join(vault, "C.md"))
    changed, deleted = tracker.get_changed_files(vault)
    assert deleted == ["C.md"]
    assert changed == []


def test_tracker_ignores_unchanged(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    tracker = CrawlStateTracker(fs)
    tracker.save_state(tracker.scan_mtimes(vault))
    # Nothing touched -> no changes, no deletions.
    changed, deleted = tracker.get_changed_files(vault)
    assert changed == []
    assert deleted == []


def test_crawl_up_to_date(tmp_path):
    vault = _make_vault(tmp_path)
    crawler, graph, fs, tracker = _crawler(vault, tracker=True)
    first = asyncio.run(crawler.crawl())
    assert first["files_scanned"] == 3
    assert first["nodes"] == 3 and first["edges"] == 2
    # State file persisted in the vault root.
    assert fs.exists(".crawl_state.json")
    # Second crawl, zero vault changes -> instant up_to_date, nothing rescanned.
    second = asyncio.run(crawler.crawl())
    assert second == {
        "status": "up_to_date",
        "files_scanned": 0,
        "nodes": 3,
        "edges": 2,
    }


def test_crawl_incremental_merge(tmp_path):
    vault = _make_vault(tmp_path)
    crawler, graph, fs, tracker = _crawler(vault, tracker=True)
    assert asyncio.run(crawler.crawl())["files_scanned"] == 3
    # Modify exactly ONE file: B.md gains a link to A.md.
    b = os.path.join(vault, "B.md")
    Path(b).write_text("leaf #done [[A.md]]", encoding="utf-8")
    _bump_mtime(b)
    stats = asyncio.run(crawler.crawl())
    assert stats["files_scanned"] == 1  # ONLY the changed file was rescanned
    g = graph.get_graph()
    # Graph is correct: 3 nodes, edges = A->B, A->C (incoming edge to B
    # survives the differential update) + new B->A.
    assert len(g["nodes"]) == 3
    edges = sorted((e["from"], e["to"]) for e in g["edges"])
    assert edges == [("A.md", "B.md"), ("A.md", "C.md"), ("B.md", "A.md")]
    # B's node meta was refreshed (new tag).
    b_node = next(n for n in g["nodes"] if n["id"] == "B.md")
    assert b_node["meta"]["tags"] == ["done"]
    # Deletion is differential too: remove C.md -> node + its edge vanish.
    os.remove(os.path.join(vault, "C.md"))
    stats2 = asyncio.run(crawler.crawl())
    assert stats2["files_scanned"] == 0
    g2 = graph.get_graph()
    assert sorted(n["id"] for n in g2["nodes"]) == ["A.md", "B.md"]
    assert sorted((e["from"], e["to"]) for e in g2["edges"]) == [
        ("A.md", "B.md"), ("B.md", "A.md"),
    ]


def test_zero_regression_without_tracker(tmp_path):
    vault = _make_vault(tmp_path)
    crawler, graph, fs, _ = _crawler(vault, tracker=None)
    # tracker=None -> Stage-10 behavior: full rescan every time.
    first = asyncio.run(crawler.crawl())
    assert first == {"files_scanned": 3, "nodes": 3, "edges": 2}
    assert "status" not in first
    # Second crawl WITHOUT changes still rescans everything (no up_to_date).
    second = asyncio.run(crawler.crawl())
    assert second == {"files_scanned": 3, "nodes": 3, "edges": 2}
    # And no state file is ever written.
    assert not fs.exists(".crawl_state.json")
