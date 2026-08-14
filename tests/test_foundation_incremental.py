"""STAGE 4 S4.3 — incremental ingest (ТЗ-KNOWLEDGE-INCREMENTAL-01).

Verifies build_incremental() merges only NEW sidecars into an existing
snapshot without a full rebuild, and never mutates the input snapshot.

SAFETY: fully isolated temp fixtures; no production snapshot read/write.
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

from scripts.foundation_ingest import build_incremental  # noqa: E402
from composition.knowledge_persistence import KnowledgeSnapshotStore  # noqa: E402


def _write_fake_snapshot(tmp: Path):
    snap = tmp / "_snapshot.json"
    payload = {
        "version": 1,
        "graph": {
            "nodes": [
                {
                    "id": "KROFT-FND-francis_bacon_novum_organum-001",
                    "label": "idols",
                    "meta": {"source": {"id": "francis_bacon_novum_organum.pdf"}},
                }
            ],
            "edges": [],
        },
        "index": {},
        "semantic_vectors": {"KROFT-FND-francis_bacon_novum_organum-001": [0.1, 0.2]},
    }
    KnowledgeSnapshotStore(str(snap)).save(
        graph_state=payload["graph"],
        index_state=payload["index"],
        semantic_vectors=payload["semantic_vectors"],
        destructive=True,
    )
    return str(snap)


def _write_new_sidecar(tmp: Path):
    ext = tmp / "_extracted"
    ext.mkdir(exist_ok=True)
    sidecar = ext / "wiener_cybernetics.json"
    sidecar.write_text(json.dumps({
        "meta": {"status": "OK", "title": "Cybernetics", "author": "Norbert Wiener"},
        "chunks": [
            {"text": "cybernetics control communication", "page_start": 1, "page_end": 2},
            {"text": "feedback loop animal machine", "page_start": 3, "page_end": 4},
        ],
    }), encoding="utf-8")
    return str(ext)


def test_incremental_merges_new_sidecar_only():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_incr_"))
    snap = _write_fake_snapshot(tmp)
    ext = _write_new_sidecar(tmp)
    out = str(tmp / "merged.json")

    report = build_incremental(snap, extracted_dir=ext, output_path=out, skip_embed=True)

    # 2 new chunk nodes added (wiener has 2 chunks), 0 skipped (bacon not in extracted)
    assert report["added_nodes"] == 2, report
    assert report["total_nodes"] == 3, report  # 1 existing + 2 new

    merged = KnowledgeSnapshotStore(out).load()
    ids = {n["id"] for n in merged["graph"]["nodes"]}
    assert "KROFT-FND-francis_bacon_novum_organum-001" in ids, "existing node lost!"
    assert "KROFT-FND-wiener_cybernetics-001" in ids
    assert "KROFT-FND-wiener_cybernetics-002" in ids


def test_incremental_skips_already_present():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_incr_skip_"))
    snap = _write_fake_snapshot(tmp)
    # extracted dir CONTAINS the already-ingested bacon sidecar -> must be skipped
    ext = tmp / "_extracted"
    ext.mkdir(exist_ok=True)
    (ext / "francis_bacon_novum_organum.json").write_text(json.dumps({
        "meta": {"status": "OK", "title": "Novum Organum", "author": "Francis Bacon"},
        "chunks": [{"text": "idols of the mind", "page_start": 1, "page_end": 1}],
    }), encoding="utf-8")
    out = str(tmp / "merged.json")

    report = build_incremental(snap, extracted_dir=str(ext), output_path=out, skip_embed=True)
    assert report["added_nodes"] == 0, report
    assert report["skipped_works"] == 1, report
    assert report["total_nodes"] == 1, report


def test_incremental_never_mutates_input():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_incr_ro_"))
    snap = _write_fake_snapshot(tmp)
    ext = _write_new_sidecar(tmp)
    before = open(snap, "rb").read()

    build_incremental(snap, extracted_dir=ext, output_path=str(tmp / "merged.json"), skip_embed=True)

    after = open(snap, "rb").read()
    assert before == after, "input snapshot must not be mutated"
