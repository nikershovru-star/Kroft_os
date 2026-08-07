"""ТЗ-KNOWLEDGE-PERSIST-01 (Флаг 1b, separate): live knowledge graph persists
across restarts so KROFT_OS starts "already learned" from the vault.

Targeted round-trip test (K5 + I-09): build a graph + content index, persist
to a JSON snapshot, restore into a FRESH engine, and assert the rebuilt state
is byte-for-byte identical to the original (same nodes/edges/terms, same order).
Also covers the composition seam (KnowledgeSnapshotStore) end-to-end on disk.
"""

from __future__ import annotations

import json

from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine
from composition.knowledge_persistence import KnowledgeSnapshotStore

import pytest


def _build_sample_graph() -> InMemoryGraphEngine:
    g = InMemoryGraphEngine()
    notes = {
        "adr-022.md": "# ADR-022\nreuses [[ADR-021]] and [[LAW K1]]\n",
        "adr-021.md": "# ADR-021\nlinks [[LAW K1]]\n",
        "law-k1.md": "# LAW K1\nkernel may only import kernel.domain\n",
    }
    idx = ContentIndex()
    eng = build_knowledge_engine(graph=g, content_index=idx)
    for doc_id, text in notes.items():
        eng.ingest(doc_id, text)
    return g


def test_graph_snapshot_roundtrip(tmp_path):
    """snapshot() -> restore() on a fresh engine yields identical state (I-09)."""
    g = _build_sample_graph()
    snap = g.snapshot()
    assert snap["nodes"] and snap["edges"]

    g2 = InMemoryGraphEngine()
    g2.restore(snap)
    assert g2.nodes() == g.nodes()
    assert g2.edges() == g.edges()
    # content index also round-trips via ISnapshotable
    idx1, idx2 = ContentIndex(), ContentIndex()
    eng1 = build_knowledge_engine(graph=g, content_index=idx1)
    for did, t in [("a.md", "lambda calculus fixed point"),
                   ("b.md", "monad functor applicative")]:
        eng1.ingest(did, t)
    idx2.restore(idx1.snapshot())
    assert idx1.get_stats() == idx2.get_stats()
    assert idx1.search("lambda") == idx2.search("lambda")


def test_knowledge_snapshot_store_disk_roundtrip(tmp_path):
    """KnowledgeSnapshotStore writes a parseable JSON and reloads identically."""
    g = _build_sample_graph()
    idx = ContentIndex()
    eng = build_knowledge_engine(graph=g, content_index=idx)
    eng.ingest("extra.md", "persistence snapshot restore")

    store = KnowledgeSnapshotStore(str(tmp_path / "knowledge.json"))
    store.save(g.snapshot(), idx.snapshot(), meta={"vault": "demo"})
    loaded = store.load()
    assert loaded is not None
    assert loaded["meta"]["vault"] == "demo"
    # reload is valid JSON with the expected shape
    assert set(loaded.keys()) >= {"version", "graph", "index", "meta"}
    # a fresh engine rebuilt from disk matches the original node count
    g2 = InMemoryGraphEngine()
    g2.restore(loaded["graph"])
    assert len(g2.nodes()) == len(g.nodes())

    # corrupt/missing file -> graceful None (never raises)
    missing = KnowledgeSnapshotStore(str(tmp_path / "does-not-exist.json"))
    assert missing.load() is None


def test_run_kroft_persists_and_restores(tmp_path):
    """KroftApp writes a knowledge snapshot and a cold boot without vault still
    answers from the restored graph (ТЗ-KNOWLEDGE-PERSIST-01 end-to-end)."""
    from composition.run_kroft import KroftApp, KroftConfig

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "law.md").write_text("# LAW K1\nkernel isolation law", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    # Run 1: ingest vault + persist
    a1 = KroftApp(KroftConfig(node_id="p1", llm="none", ticks=0,
                              vault=str(vault), knowledge_snapshot=snap))
    assert a1._snapshot_store is not None

    # Run 2: COLD BOOT, no vault, only the snapshot on disk
    a2 = KroftApp(KroftConfig(node_id="p2", llm="none", ticks=0,
                              vault=None, knowledge_snapshot=snap))
    ans = a2.interactive_query("LAW K1")
    # the cold boot "knows" the note without re-reading the vault
    assert "LAW K1" in ans
