"""STAGE 4 S4.4 — autonomous ingest step (ТЗ-KNOWLEDGE-AUTONOMOUS-01).

One autonomous step: detect a catalog gap (entry present in YAML but missing from
graph) whose sidecar is on disk, then merge it incrementally into a TEMP copy.

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

from scripts.foundation_ingest import autonomous_ingest_step  # noqa: E402
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


def _write_catalog_with_wiener(tmp: Path):
    cat = tmp / "catalog.yaml"
    cat.write_text(
        "core_v1:\n"
        "  - author: \"Francis Bacon\"\n"
        "    title: \"Novum Organum\"\n"
        "    legal: public_domain\n"
        "    filename:\n"
        "      - francis_bacon_novum_organum\n"
        "  - author: \"Norbert Wiener\"\n"
        "    title: \"Cybernetics\"\n"
        "    legal: public_domain\n"
        "    filename:\n"
        "      - norbert_wiener_cybernetics\n",
        encoding="utf-8",
    )
    return str(cat)


def _write_wiener_sidecar(tmp: Path):
    ext = tmp / "_extracted"
    ext.mkdir(exist_ok=True)
    (ext / "norbert_wiener_cybernetics.json").write_text(json.dumps({
        "meta": {"status": "OK", "title": "Cybernetics", "author": "Norbert Wiener"},
        "chunks": [{"text": "cybernetics control", "page_start": 1, "page_end": 1}],
    }), encoding="utf-8")
    return str(ext)


def test_autonomous_step_detects_and_ingests_gap():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_auto_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog_with_wiener(tmp)
    ext = _write_wiener_sidecar(tmp)
    out = str(tmp / "auto.json")

    result = autonomous_ingest_step(snap, cat, extracted_dir=ext, output_path=out)

    assert result["ingested"] is True, result
    assert "norbert_wiener_cybernetics" in result["gap_entries"], result
    assert result["report"]["added_nodes"] == 1, result

    merged = KnowledgeSnapshotStore(out).load()
    ids = {n["id"] for n in merged["graph"]["nodes"]}
    assert "KROFT-FND-norbert_wiener_cybernetics-001" in ids
    assert "KROFT-FND-francis_bacon_novum_organum-001" in ids  # preserved


def test_autonomous_step_no_gap_is_noop():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_auto_noop_"))
    snap = _write_fake_snapshot(tmp)
    # catalog contains ONLY the already-present bacon -> no gap
    cat = tmp / "catalog.yaml"
    cat.write_text(
        "core_v1:\n"
        "  - author: \"Francis Bacon\"\n"
        "    title: \"Novum Organum\"\n"
        "    legal: public_domain\n"
        "    filename:\n"
        "      - francis_bacon_novum_organum\n",
        encoding="utf-8",
    )
    ext = tmp / "_extracted"
    ext.mkdir(exist_ok=True)
    out = str(tmp / "auto.json")

    result = autonomous_ingest_step(snap, str(cat), extracted_dir=str(ext), output_path=out)
    assert result["ingested"] is False, result
    assert result["gap_entries"] == [], result


def test_autonomous_step_never_mutates_input():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_auto_ro_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog_with_wiener(tmp)
    ext = _write_wiener_sidecar(tmp)
    before = open(snap, "rb").read()

    autonomous_ingest_step(snap, cat, extracted_dir=ext, output_path=str(tmp / "auto.json"))

    after = open(snap, "rb").read()
    assert before == after, "input snapshot must not be mutated"
