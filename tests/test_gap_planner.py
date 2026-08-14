"""STAGE 5 V1 — knowledge-gap planner (ТЗ-KNOWLEDGE-GAP-PLANNER-01).

GapPlanner turns a detected gap (0 hits / goal) into a ranked ingest plan from
the catalog, WITHOUT mutating the snapshot (pure planning).

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

from scripts.foundation_ingest import GapPlanner  # noqa: E402
from composition.knowledge_persistence import KnowledgeSnapshotStore  # noqa: E402


def _write_fake_snapshot(tmp: Path):
    snap = tmp / "_snapshot.json"
    KnowledgeSnapshotStore(str(snap)).save(
        graph_state={"nodes": [
            {"id": "KROFT-FND-francis_bacon_novum_organum-001",
             "label": "idols",
             "meta": {"source": {"id": "francis_bacon_novum_organum.pdf"}}},
        ], "edges": []},
        index_state={},
        semantic_vectors={"KROFT-FND-francis_bacon_novum_organum-001": [0.1, 0.2]},
        destructive=True,
    )
    return str(snap)


def _write_catalog(tmp: Path):
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


def test_plan_ranks_actionable_gaps_by_goal_overlap():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)

    planner = GapPlanner(snap, cat, extracted_dir=ext)
    plan = planner.plan(goals=["cybernetics control theory"])

    assert plan["gaps_total"] == 1, plan
    assert plan["actionable"] == 1, plan
    action = plan["actions"][0]
    assert action["stem"] == "norbert_wiener_cybernetics", action
    assert action["has_sidecar"] is True
    assert action["goal_overlap"] >= 1, action  # "cybernetics" overlaps title


def test_plan_present_entries_excluded():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_present_"))
    snap = _write_fake_snapshot(tmp)  # bacon already present
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)

    planner = GapPlanner(snap, cat, extracted_dir=ext)
    plan = planner.plan()  # no goals -> full catalog gaps

    stems = {a["stem"] for a in plan["actions"]}
    assert "francis_bacon_novum_organum" not in stems, "present entry must be excluded"
    assert "norbert_wiener_cybernetics" in stems


def test_plan_is_pure_no_snapshot_mutation():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_ro_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)
    before = open(snap, "rb").read()

    GapPlanner(snap, cat, extracted_dir=ext).plan(goals=["cybernetics"])

    assert open(snap, "rb").read() == before, "plan() must not mutate snapshot"
