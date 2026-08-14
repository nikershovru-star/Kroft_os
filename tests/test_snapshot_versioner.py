"""STAGE 5 V3 — safe recovery / rollback (ТЗ-KNOWLEDGE-SAFE-RECOVERY-01).

Versioned snapshot copies + sha256 manifest + reversible rollback.
SAFETY: isolated temp fixtures; no production snapshot read/write.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from composition.knowledge_persistence import KnowledgeSnapshotStore, SnapshotVersioner  # noqa: E402


def _write_snapshot(path: str, payload: dict):
    KnowledgeSnapshotStore(path).save(
        graph_state=payload.get("graph", {"nodes": [], "edges": []}),
        index_state=payload.get("index", {}),
        semantic_vectors=payload.get("semantic_vectors"),
        destructive=True,
    )


def test_save_version_creates_immutable_copy():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_v3_"))
    snap = str(tmp / "_snapshot.json")
    _write_snapshot(snap, {"graph": {"nodes": [{"id": "a"}], "edges": []},
                            "semantic_vectors": {"a": [0.1]}})
    original_sha = KnowledgeSnapshotStore(snap).load_semantic_vectors()

    ver = SnapshotVersioner(snap)
    v1 = ver.save_version(label="initial")
    assert v1 is not None
    versions = ver.list_versions()
    assert len(versions) == 1
    assert versions[0]["label"] == "initial"
    # canonical unchanged, version file is a copy
    assert KnowledgeSnapshotStore(snap).load_semantic_vectors() == original_sha
    assert os.path.isfile(versions[0]["path"])


def test_rollback_is_reversible():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_v3_roll_"))
    snap = str(tmp / "_snapshot.json")

    _write_snapshot(snap, {"graph": {"nodes": [{"id": "v1"}], "edges": []},
                            "semantic_vectors": {"v1": [1.0]}})
    v1_path = SnapshotVersioner(snap).save_version(label="v1")

    # mutate canonical -> v2
    _write_snapshot(snap, {"graph": {"nodes": [{"id": "v2"}], "edges": []},
                            "semantic_vectors": {"v2": [2.0]}})
    SnapshotVersioner(snap).save_version(label="v2")

    # rollback to v1
    ver = SnapshotVersioner(snap)
    ver.rollback(1)
    restored = KnowledgeSnapshotStore(snap).load()
    assert restored["graph"]["nodes"][0]["id"] == "v1"

    # the pre-rollback canonical (v2) must be preserved as a new version
    versions = ver.list_versions()
    labels = [v["label"] for v in versions]
    assert any("pre-rollback" in l for l in labels), labels
    assert os.path.isfile(v1_path), "v1 immutable copy must survive rollback"


def test_rollback_unknown_version_raises():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_v3_bad_"))
    snap = str(tmp / "_snapshot.json")
    _write_snapshot(snap, {"graph": {"nodes": []}, "edges": []}, )
    ver = SnapshotVersioner(snap)
    with pytest.raises(ValueError):
        ver.rollback(99)


def test_no_version_when_snapshot_absent():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_v3_none_"))
    snap = str(tmp / "_snapshot.json")  # never written
    ver = SnapshotVersioner(snap)
    assert ver.save_version() is None
    assert ver.list_versions() == []
