"""L10.7 — Atomic Persistence + Capacity Guards (isolated, no production data).

Tests A-F from ТЗ-L10.7:
  A. atomic snapshot — simulated failure leaves original valid
  B. atomic session   — simulated failure leaves original valid
  C. episode capacity — FIFO retention (max=3 -> len 3, oldest removed)
  D. semantic capacity — FIFO retention
  E. normative capacity — FIFO retention
  F. restart           — save -> new runtime -> restore, capacity preserved
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest import mock

from contracts.cognitive_domain import (
    Episode, Policy, PolicyLifecycle, SemanticFact,
    ConfidenceScore, Provenance, ProvenanceType, CausalMark,
)
from kernel.memory_store import InMemoryLayeredMemory
from composition.knowledge_persistence import KnowledgeSnapshotStore
from services.session_store import SessionStore


def _ep(i: int) -> Episode:
    return Episode(
        id=f"e{i}", summary=f"s{i}",
        confidence=ConfidenceScore(0.5, ProvenanceType.OBSERVATION),
        provenance=Provenance(source="agent:test", actor="test"),
    )


def _fact(i: int) -> SemanticFact:
    return SemanticFact(
        id=f"f{i}", content=f"c{i}",
        confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION),
        causal=CausalMark(node_origin="test", lamport=i),
    )


def _pol(i: int) -> Policy:
    return Policy(
        id=f"p{i}", name=f"n{i}", layer="soft", body="b",
        confidence=ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE),
        provenance=Provenance(source="rule:test", actor="test"),
        lifecycle=PolicyLifecycle.ACTIVE,
    )


# ---- Test A: atomic snapshot ----
def test_A_atomic_snapshot_failure_keeps_original():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "snap.json")
    store = KnowledgeSnapshotStore(path)
    # valid baseline write
    store.save({}, {}, meta={"v": 1})
    assert os.path.isfile(path)
    with open(path) as f:
        before = json.load(f)
    # simulate failure on the final atomic rename
    with mock.patch("os.replace", side_effect=OSError("boom")):
        try:
            store.save({}, {}, meta={"v": 2})
        except OSError:
            pass
    # original file must still be valid + unchanged (only .tmp may linger)
    assert os.path.isfile(path)
    with open(path) as f:
        after = json.load(f)
    assert after == before
    assert after.get("meta", {}).get("v") == 1


# ---- Test B: atomic session ----
def test_B_atomic_session_failure_keeps_original():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "session.json")
    s = SessionStore(persistence_path=path, max_turns=50)
    s.add_turn("cmd1", "find", "r1")
    assert os.path.isfile(path)
    with open(path) as f:
        before = json.load(f)
    with mock.patch("os.replace", side_effect=OSError("boom")):
        try:
            s.add_turn("cmd2", "find", "r2")
        except OSError:
            pass
    assert os.path.isfile(path)
    with open(path) as f:
        after = json.load(f)
    assert after == before  # original untouched


# ---- Test C: episode capacity ----
def test_C_episode_capacity_fifo():
    m = InMemoryLayeredMemory(max_episodes=3)
    for i in range(4):
        m.record_episode(_ep(i))
    assert len(m.get_episodes()) == 3
    ids = [e.id for e in m.get_episodes()]
    assert ids == ["e1", "e2", "e3"]  # e0 (oldest) dropped
    # boundary: N-1 and N both kept
    m2 = InMemoryLayeredMemory(max_episodes=3)
    m2.record_episode(_ep(0))
    m2.record_episode(_ep(1))
    assert len(m2.get_episodes()) == 2


# ---- Test D: semantic capacity ----
def test_D_semantic_capacity_fifo():
    m = InMemoryLayeredMemory(max_semantic=3)
    for i in range(4):
        m.commit_semantic(_fact(i))
    assert len(m.get_semantic()) == 3
    ids = [f.id for f in m.get_semantic()]
    assert ids == ["f1", "f2", "f3"]


# ---- Test E: normative capacity ----
def test_E_normative_capacity_fifo():
    m = InMemoryLayeredMemory(max_normative=3)
    for i in range(4):
        m.commit_normative(_pol(i))
    assert len(m.get_normative()) == 3
    ids = [p.id for p in m.get_normative()]
    assert ids == ["p1", "p2", "p3"]


# ---- Test F: restart + capacity preservation ----
def test_F_restart_capacity_preserved():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "rt.json")
    store = KnowledgeSnapshotStore(path)
    m = InMemoryLayeredMemory(max_episodes=3)
    for i in range(5):  # write more than capacity
        m.record_episode(_ep(i))
    assert len(m.get_episodes()) == 3
    # persist (only episodes + meta; graph/index empty like runtime store)
    store.save({"nodes": [], "edges": []}, {"_index": {}, "_doc_terms": {}},
               meta={"kind": "runtime"},
               episodes=[{"id": e.id, "summary": e.summary,
                         "confidence": e.confidence.value,
                         "provenance": None} for e in m.get_episodes()])
    # new runtime: restore
    store2 = KnowledgeSnapshotStore(path)
    blobs = store2.load_episodic()
    assert len(blobs) == 3  # capacity preserved across restart
    assert [b["id"] for b in blobs] == ["e2", "e3", "e4"]


def test_G_corruption_safe_load_preserves_dot_corrupt():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "snap.json")
    with open(path, "w") as f:
        f.write("{ this is not valid json ")
    store = KnowledgeSnapshotStore(path)
    assert store.load() is None  # graceful degrade
    assert os.path.isfile(path + ".corrupt")  # broken file preserved
