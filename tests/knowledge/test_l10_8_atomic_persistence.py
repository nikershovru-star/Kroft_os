"""L10.8 — KnowledgeSnapshotStore atomic persistence isolation (ТЗ-L10.8).

Failure-injection tests for the surgical atomic-save fix in
composition/knowledge_persistence.py. Isolated (temp dirs, no production data).

  A. atomic replacement failure -> original snapshot valid + unchanged
  B. successful atomic save -> reload yields identical logical payload
  C. corrupted snapshot -> load() == None and <snapshot>.corrupt preserved
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

from composition.knowledge_persistence import KnowledgeSnapshotStore


def _write_valid(path: str) -> dict:
    store = KnowledgeSnapshotStore(path)
    payload = {
        "graph": {"nodes": [], "edges": []},
        "index": {"_index": {}, "_doc_terms": {}},
        "meta": {"kind": "runtime", "v": 1},
        "trust": {},
        "procedural": {},
        "episodes": [{"id": "e1", "summary": "s1", "confidence": 0.5, "provenance": None}],
        "semantic": [],
        "normative": [],
    }
    store.save(
        payload["graph"], payload["index"], meta=payload["meta"],
        trust=payload["trust"], procedural=payload["procedural"],
        episodes=payload["episodes"], semantic=payload["semantic"],
        normative=payload["normative"],
    )
    return payload


# ---- A: atomic replacement failure keeps original valid ----
def test_A_atomic_replacement_failure_keeps_original():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "snap.json")
    _write_valid(path)
    with open(path) as f:
        before = json.load(f)
    # simulate failure on the final atomic rename
    with mock.patch("os.replace", side_effect=OSError("boom")):
        try:
            KnowledgeSnapshotStore(path).save(
                {"nodes": [], "edges": []}, {"_index": {}, "_doc_terms": {}},
                meta={"kind": "runtime", "v": 2})
        except OSError:
            pass
    # original file must still be valid + unchanged (only .tmp may linger)
    assert os.path.isfile(path)
    with open(path) as f:
        after = json.load(f)
    assert after == before
    assert after["meta"]["v"] == 1


# ---- B: successful atomic save reloads identical logical payload ----
def test_B_successful_atomic_save_reloads():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "snap.json")
    payload = _write_valid(path)
    reloaded = KnowledgeSnapshotStore(path).load()
    assert reloaded is not None
    assert reloaded["episodes"] == payload["episodes"]
    assert reloaded["meta"] == payload["meta"]
    # no stray .tmp left behind after a successful save
    assert not os.path.exists(path + ".tmp")


# ---- C: corrupted snapshot -> None + .corrupt preserved ----
def test_C_corrupted_snapshot_recovers():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "snap.json")
    with open(path, "w") as f:
        f.write("{ this is not valid json ")
    assert KnowledgeSnapshotStore(path).load() is None
    assert os.path.isfile(path + ".corrupt")  # broken file preserved
