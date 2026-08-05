"""Stage 18 - Content Indexing & Full-Text Search tests (8).

ContentIndex (services/content_index.py) inverted index + integration with
VaultStreamCrawler (write path) and GraphQueryEngine (read path).
Incremental reindex uses a real tmp vault + os.utime-forced mtime bumps
(same convention as tests/test_incremental.py).

Gate mapping:
  Search       -> test_search_and_logic / test_search_case_insensitive
  Regression   -> test_zero_regression_without_index
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from adapters import LocalFileSystemAdapter
from infrastructure import InMemoryGraphBuilder, InMemoryEventBus
from services import (
    VaultStreamCrawler,
    GraphQueryEngine,
    CrawlStateTracker,
    ContentIndex,
)


# --------------------------------------------------------------------------
# Unit level: ContentIndex alone
# --------------------------------------------------------------------------
def test_index_file_adds_terms():
    ix = ContentIndex()
    ix.index_file("A.md", "Python architecture notes")
    assert ix.search("python") == ["A.md"]
    assert ix.search("architecture") == ["A.md"]
    # Tokens shorter than 2 chars are never indexed.
    ix.index_file("B.md", "a b c x y z")
    assert ix.search("a") == []
    assert ix.get_stats()["documents"] == 1  # B.md had no indexable terms


def test_search_and_logic():
    ix = ContentIndex()
    ix.index_file("A.md", "python testing guide")
    ix.index_file("B.md", "python cooking blog")
    ix.index_file("C.md", "testing kitchen scales")
    # Single terms hit their own posting lists.
    assert set(ix.search("python")) == {"A.md", "B.md"}
    assert set(ix.search("testing")) == {"A.md", "C.md"}
    # AND: only the doc containing BOTH terms survives the intersection.
    assert ix.search("python testing") == ["A.md"]
    # AND with a term nobody has -> [].
    assert ix.search("python nonexistent") == []


def test_search_case_insensitive():
    ix = ContentIndex()
    ix.index_file("A.md", "Hello World")
    ix.index_file("B.md", "hello there")
    # 'Hello' and 'hello' land in ONE posting list; query case is irrelevant.
    assert set(ix.search("hello")) == {"A.md", "B.md"}
    assert set(ix.search("HELLO")) == {"A.md", "B.md"}
    assert ix.search("WoRlD") == ["A.md"]


def test_remove_file_clears_terms():
    ix = ContentIndex()
    ix.index_file("A.md", "unique singleton content")
    ix.index_file("B.md", "shared content here")
    ix.remove_file("A.md")
    assert ix.search("unique") == []
    assert ix.search("singleton") == []
    # Shared term survives for the remaining doc.
    assert ix.search("content") == ["B.md"]
    # Removing an unknown doc is a silent no-op.
    ix.remove_file("nope.md")
    assert ix.get_stats()["documents"] == 1


def test_search_no_match():
    ix = ContentIndex()
    ix.index_file("A.md", "some indexed words")
    assert ix.search("missingword") == []
    assert ix.search("") == []          # empty query
    assert ix.search("x") == []         # below min token length
    assert ix.search("!!! ---") == []   # no \w+ tokens at all


def test_index_stats():
    ix = ContentIndex()
    assert ix.get_stats() == {"terms": 0, "documents": 0}
    ix.index_file("A.md", "alpha beta gamma")
    ix.index_file("B.md", "beta delta")
    st = ix.get_stats()
    assert st["documents"] == 2
    assert st["terms"] == 4  # alpha, beta, gamma, delta (beta shared)
    ix.remove_file("A.md")
    st2 = ix.get_stats()
    assert st2 == {"terms": 2, "documents": 1}  # beta, delta remain


# --------------------------------------------------------------------------
# Integration: crawler write path + query engine read path
# --------------------------------------------------------------------------
def _make_vault(tmp_path: Path) -> str:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text("Python architecture [[B.md]]", encoding="utf-8")
    (vault / "B.md").write_text("python testing #todo", encoding="utf-8")
    (vault / "C.md").write_text("cooking recipes", encoding="utf-8")
    return str(vault)


def _bump_mtime(path: str, offset: float = 10.0) -> None:
    t = time.time() + offset
    os.utime(path, (t, t))


def test_incremental_reindex(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    graph = InMemoryGraphBuilder()
    ix = ContentIndex()
    crawler = VaultStreamCrawler(
        fs, InMemoryEventBus(), graph, vault,
        tracker=CrawlStateTracker(fs), index=ix,
    )
    engine = GraphQueryEngine(graph, index=ix)
    asyncio.run(crawler.crawl())
    assert set(engine.search("python")) == {"A.md", "B.md"}
    # Change B.md: 'python testing' -> 'gardening tips'.
    b = os.path.join(vault, "B.md")
    Path(b).write_text("gardening tips #hobby", encoding="utf-8")
    _bump_mtime(b)
    stats = asyncio.run(crawler.crawl())
    assert stats["files_scanned"] == 1  # incremental: only B.md rescanned
    # Old terms gone, new terms present — no stale postings.
    assert engine.search("python") == ["A.md"]
    assert engine.search("testing") == []
    assert engine.search("gardening") == ["B.md"]
    # Deleted file leaves the index too.
    os.remove(os.path.join(vault, "C.md"))
    asyncio.run(crawler.crawl())
    assert engine.search("cooking") == []
    assert ix.get_stats()["documents"] == 2


def test_zero_regression_without_index(tmp_path):
    vault = _make_vault(tmp_path)
    fs = LocalFileSystemAdapter(vault)
    graph = InMemoryGraphBuilder()
    # index=None everywhere -> Stage-17 behavior, search returns [].
    crawler = VaultStreamCrawler(fs, InMemoryEventBus(), graph, vault)
    engine = GraphQueryEngine(graph)
    stats = asyncio.run(crawler.crawl())
    assert stats == {"files_scanned": 3, "nodes": 3, "edges": 1}
    assert engine.search("python") == []
    assert engine.search("anything at all") == []
    # Structural queries unaffected.
    assert engine.backlinks("B.md") == ["A.md"]
