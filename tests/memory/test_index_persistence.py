"""Stage 19 - Index Persistence tests (8).

ContentIndex implements ISnapshotable; Kernel restores it from
data/index_snapshot.json on initialize() and writes it on save()/stop();
the Stage-18 in-memory-only rebuild (ensure_index) is gone, so a cold CLI/REPL
start is O(1). SnapshotStore writes atomically (tmp + rename).
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from adapters import LocalFileSystemAdapter
from infrastructure import InMemoryGraphBuilder, InMemoryEventBus, SnapshotStore
from infrastructure.state_repository import StateRepository
from services import ContentIndex, GraphQueryEngine, VaultStreamCrawler, CrawlStateTracker
from contracts import ISnapshotable
from kernel import Kernel
from main import build_container


# --------------------------------------------------------------------------
# 1. ContentIndex.snapshot / restore round-trip
# --------------------------------------------------------------------------
def test_content_index_snapshot_roundtrip():
    ix = ContentIndex()
    ix.index_file("A.md", "hello world hello")
    ix.index_file("B.md", "world python")

    snap = ix.snapshot()
    # snapshot is a plain dict (JSON-serializable, no sets/Counter).
    json.dumps(snap)

    ix2 = ContentIndex()
    ix2.restore(snap)

    assert ix2.search("hello") == ["A.md"]
    assert set(ix2.search("world")) == {"A.md", "B.md"}
    assert ix2.get_stats() == ix.get_stats()


# --------------------------------------------------------------------------
# 2. SnapshotStore atomic write (tmp + rename)
# --------------------------------------------------------------------------
def test_snapshot_store_atomic_write(tmp_path):
    fs = LocalFileSystemAdapter(str(tmp_path))
    store = SnapshotStore(fs, "snap.json")
    store.save({"version": 2, "graph": {}, "index": {}})
    assert json.loads(fs.read_content("snap.json"))["version"] == 2
    # The temp file was renamed away (no leftover .tmp).
    assert not fs.exists("snap.json.tmp")


# --------------------------------------------------------------------------
# 3. SnapshotStore load round-trips arbitrary payloads
# --------------------------------------------------------------------------
def test_snapshot_store_load_roundtrip(tmp_path):
    fs = LocalFileSystemAdapter(str(tmp_path))
    store = SnapshotStore(fs, "snap.json")
    payload = {"version": 2, "index": {"_index": {"x": ["A.md"]}, "_doc_terms": {}}}
    store.save(payload)
    assert store.load() == payload


# --------------------------------------------------------------------------
# 4. ISnapshotable contract is implemented by ContentIndex (runtime_checkable)
# --------------------------------------------------------------------------
def test_content_index_is_snapshotable():
    assert isinstance(ContentIndex(), ISnapshotable)


# --------------------------------------------------------------------------
# 5. Kernel restores the index from a v2 snapshot on a fresh process
# --------------------------------------------------------------------------
def _seed_vault(vault: str) -> None:
    Path(vault).mkdir(parents=True, exist_ok=True)
    (Path(vault) / "A.md").write_text("python guide", encoding="utf-8")
    (Path(vault) / "B.md").write_text("rust guide", encoding="utf-8")


def test_kernel_restores_index_from_v2_snapshot(tmp_path):
    vault = str(tmp_path / "vault")
    _seed_vault(vault)

    # First process: crawl + stop (persists graph + index snapshot).
    c1 = build_container(vault)
    k1 = Kernel(c1)
    k1.initialize()
    k1.start()
    asyncio.run(c1.resolve("VaultStreamCrawler").crawl())
    k1.stop()

    # Second process: fresh container + kernel, cold start.
    c2 = build_container(vault)
    k2 = Kernel(c2)
    k2.initialize()
    assert isinstance(k2._state_repository, StateRepository)

    engine = c2.resolve("GraphQueryEngine")
    # Index restored from snapshot — no re-crawl.
    assert engine.search("python") == ["A.md"]
    assert set(engine.search("guide")) == {"A.md", "B.md"}


# --------------------------------------------------------------------------
# 6. Kernel.save() writes a v2 snapshot with the index
# --------------------------------------------------------------------------
def test_kernel_saves_v2_snapshot(tmp_path):
    vault = str(tmp_path)
    _seed_vault(vault)

    c = build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    asyncio.run(c.resolve("VaultStreamCrawler").crawl())
    k.save()  # persists index while still RUNNING

    raw = c.resolve("IFileSystem").read_content("data/state.json")
    data = json.loads(raw)
    assert data.get("version") == 2
    assert "index" in data
    assert data["index"]["_index"].get("python") == ["A.md"]


# --------------------------------------------------------------------------
# 7. Backward compat: a v1 snapshot (no "index" key) loads with empty index
# --------------------------------------------------------------------------
def test_v1_snapshot_backward_compatible(tmp_path):
    fs = LocalFileSystemAdapter(str(tmp_path))
    store = SnapshotStore(fs, "data/index_snapshot.json")
    # Old shape: graph-only, no index key.
    store.save({"version": 1, "graph": {"nodes": [], "edges": []}})

    from infrastructure import DependencyContainer
    c = DependencyContainer()
    c.register_instance("IFileSystem", fs)
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ContentIndex", ContentIndex())

    k = Kernel(c)
    k.initialize()  # must not raise on the v1 payload

    ix = c.resolve("ContentIndex")
    assert ix.get_stats()["documents"] == 0


# --------------------------------------------------------------------------
# 8. remove_file after restore keeps the index consistent
# --------------------------------------------------------------------------
def test_remove_file_after_restore():
    ix = ContentIndex()
    ix.index_file("A.md", "term")
    snap = ix.snapshot()

    ix2 = ContentIndex()
    ix2.restore(snap)
    ix2.remove_file("A.md")

    assert ix2.search("term") == []
    assert ix2.get_stats()["documents"] == 0
    assert ix2.get_stats()["terms"] == 0


# --------------------------------------------------------------------------
# Regression: GraphQueryEngine with index=None (manual wiring) stays empty
# --------------------------------------------------------------------------
def test_engine_without_index_returns_empty(tmp_path):
    vault = str(tmp_path / "vault")
    Path(vault).mkdir(parents=True, exist_ok=True)
    (Path(vault) / "A.md").write_text("python notes", encoding="utf-8")
    fs = LocalFileSystemAdapter(vault)
    graph = InMemoryGraphBuilder()
    crawler = VaultStreamCrawler(fs, InMemoryEventBus(), graph, vault)
    engine = GraphQueryEngine(graph)  # index=None -> Stage-17 behavior
    asyncio.run(crawler.crawl())
    assert engine.search("python") == []
    assert engine.backlinks("A.md") == []
