"""PHASE F — Persistence / recovery (reuse SnapshotVersioner, ТЗ §29-§30).

Verifies atomic save + version + rollback preserve semantic state (no implicit
re-embed / mutation). Uses a tiny in-memory snapshot (no production file touched).
"""

import sys
import tempfile
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.knowledge_persistence import KnowledgeSnapshotStore, SnapshotVersioner  # noqa: E402


def _state(n=3):
    return {
        "version": 1,
        "graph": {
            "nodes": [{"id": f"n{i}", "label": f"L{i}", "meta": {"type": "SOFT_FACT"}} for i in range(n)],
            "edges": [{"from": f"n{i}", "to": f"n{i+1}", "relation": "links"} for i in range(n - 1)],
        },
        "index": {"_doc_terms": {}, "_index": {}},
        "semantic_vectors": {f"n{i}": [0.1 * i, 0.2] for i in range(n)},
    }


def test_save_load_roundtrip_preserves_state():
    with tempfile.TemporaryDirectory() as tmp:
        p = str(Path(tmp) / "snap.json")
        store = KnowledgeSnapshotStore(p)
        state = _state(5)
        store.save(state["graph"], state["index"], semantic_vectors=state["semantic_vectors"])
        loaded = store.load()
        assert loaded["graph"] == state["graph"]
        assert loaded["semantic_vectors"] == state["semantic_vectors"]


def test_version_and_rollback():
    with tempfile.TemporaryDirectory() as tmp:
        p = str(Path(tmp) / "snap.json")
        store = KnowledgeSnapshotStore(p)
        store.save(_state(2)["graph"], _state(2)["index"], semantic_vectors=_state(2)["semantic_vectors"])
        ver = SnapshotVersioner(p)
        v1 = ver.save_version(label="baseline")
        assert v1 is not None
        # mutate canonical
        store.save(_state(4)["graph"], _state(4)["index"], semantic_vectors=_state(4)["semantic_vectors"])
        assert len(store.load()["graph"]["nodes"]) == 4
        # rollback to v1
        ver.rollback(1)
        assert len(store.load()["graph"]["nodes"]) == 2  # restored


def test_save_never_wipes_vectors_without_destructive():
    """ТЗ §29 safety: a save call that forgets semantic_vectors must preserve on-disk vectors."""
    with tempfile.TemporaryDirectory() as tmp:
        p = str(Path(tmp) / "snap.json")
        store = KnowledgeSnapshotStore(p)
        store.save(_state(3)["graph"], _state(3)["index"], semantic_vectors=_state(3)["semantic_vectors"])
        # re-save WITHOUT vectors (simulating a broad re-snapshot)
        store.save(_state(3)["graph"], _state(3)["index"], semantic_vectors=None)
        assert store.load()["semantic_vectors"] == _state(3)["semantic_vectors"]
