"""STAGE 5 V1 — knowledge-gap planner (ТЗ-KNOWLEDGE-GAP-PLANNER-01).

GapPlanner turns a detected gap (0 hits / goal) into a ranked ingest plan from
the catalog, WITHOUT mutating the snapshot (pure planning).

STAGE 4.7 (STEP 6): regression cases proving that only VALID, fully-extracted
sidecars (status==OK AND chunks>0) count as actionable. EXTRACTION_TIMEOUT /
EXTRACTION_FAILED sidecars (0 chunks) are NOT advertised as actionable gaps, and
identity semantics stay exact (no fuzzy match, no Russell&Norvig == Bertrand
Russell confusion, no Shannon canonical == second Shannon confusion).

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


def _write_fake_snapshot(tmp: Path, present_stems: list[str]):
    snap = tmp / "_snapshot.json"
    nodes = [
        {"id": f"KROFT-FND-{s}-001", "label": s,
         "meta": {"source": {"id": f"{s}.pdf"}}}
        for s in present_stems
    ]
    KnowledgeSnapshotStore(str(snap)).save(
        graph_state={"nodes": nodes, "edges": []},
        index_state={},
        semantic_vectors={f"KROFT-FND-{s}-001": [0.1, 0.2] for s in present_stems},
        destructive=True,
    )
    return str(snap)


def _write_catalog(tmp: Path, entries: dict):
    lines = ["core_v1:"]
    for stem, e in entries.items():
        lines.append(f"  - author: \"{e.get('author', 'X')}\"")
        lines.append(f"    title: \"{e.get('title', stem)}\"")
        lines.append(f"    legal: {e.get('legal', 'public_domain')}")
        lines.append("    filename:")
        for fn in e.get("filename", [stem]):
            lines.append(f"      - {fn}")
    cat = tmp / "catalog.yaml"
    cat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(cat)


def _write_sidecar(ext: Path, stem: str, status: str, chunks: int):
    (ext / f"{stem}.json").write_text(json.dumps({
        "meta": {"status": status, "title": stem, "author": "X"},
        "chunks": [{"text": "x", "page_start": 1, "page_end": 1}] if chunks > 0 else [],
    }), encoding="utf-8")


# --- existing V1 behaviour (kept) ---

def test_plan_ranks_actionable_gaps_by_goal_overlap():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_"))
    snap = _write_fake_snapshot(tmp, ["francis_bacon_novum_organum"])
    cat = _write_catalog(tmp, {
        "francis_bacon_novum_organum": {"author": "Francis Bacon", "title": "Novum Organum"},
        "norbert_wiener_cybernetics": {"author": "Norbert Wiener", "title": "Cybernetics"},
    })
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "norbert_wiener_cybernetics", "OK", 1)

    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan(goals=["cybernetics control theory"])
    assert plan["gaps_total"] == 1, plan
    assert plan["actionable"] == 1, plan
    action = plan["actions"][0]
    assert action["stem"] == "norbert_wiener_cybernetics", action
    assert action["has_sidecar"] is True
    assert action["goal_overlap"] >= 1, action


def test_plan_present_entries_excluded():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_present_"))
    snap = _write_fake_snapshot(tmp, ["francis_bacon_novum_organum"])
    cat = _write_catalog(tmp, {
        "francis_bacon_novum_organum": {"author": "Francis Bacon", "title": "Novum Organum"},
        "norbert_wiener_cybernetics": {"author": "Norbert Wiener", "title": "Cybernetics"},
    })
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "norbert_wiener_cybernetics", "OK", 1)

    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    stems = {a["stem"] for a in plan["actions"]}
    assert "francis_bacon_novum_organum" not in stems
    assert "norbert_wiener_cybernetics" in stems


def test_plan_is_pure_no_snapshot_mutation():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_gap_ro_"))
    snap = _write_fake_snapshot(tmp, ["francis_bacon_novum_organum"])
    cat = _write_catalog(tmp, {
        "francis_bacon_novum_organum": {"author": "Francis Bacon", "title": "Novum Organum"},
        "norbert_wiener_cybernetics": {"author": "Norbert Wiener", "title": "Cybernetics"},
    })
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "norbert_wiener_cybernetics", "OK", 1)
    before = open(snap, "rb").read()
    GapPlanner(snap, cat, extracted_dir=str(ext)).plan(goals=["cybernetics"])
    assert open(snap, "rb").read() == before


# --- STEP 6 regression cases ---

def test_case1_ok_sidecar_is_actionable():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_1_"))
    snap = _write_fake_snapshot(tmp, [])
    cat = _write_catalog(tmp, {"work_x": {"filename": ["work_x"]}})
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "work_x", "OK", 5)
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    act = [a for a in plan["actions"] if a["stem"] == "work_x"][0]
    assert act["has_sidecar"] is True


def test_case2_timeout_sidecar_not_actionable():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_2_"))
    snap = _write_fake_snapshot(tmp, [])
    cat = _write_catalog(tmp, {"work_x": {"filename": ["work_x"]}})
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "work_x", "EXTRACTION_TIMEOUT", 0)
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    act = [a for a in plan["actions"] if a["stem"] == "work_x"][0]
    assert act["has_sidecar"] is False


def test_case3_failed_sidecar_not_actionable():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_3_"))
    snap = _write_fake_snapshot(tmp, [])
    cat = _write_catalog(tmp, {"work_x": {"filename": ["work_x"]}})
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "work_x", "EXTRACTION_FAILED", 0)
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    act = [a for a in plan["actions"] if a["stem"] == "work_x"][0]
    assert act["has_sidecar"] is False


def test_case4_missing_sidecar_not_actionable():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_4_"))
    snap = _write_fake_snapshot(tmp, [])
    cat = _write_catalog(tmp, {"work_x": {"filename": ["work_x"]}})
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)  # no sidecar written
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    act = [a for a in plan["actions"] if a["stem"] == "work_x"][0]
    assert act["has_sidecar"] is False


def test_case5_russell_norvig_present_bertrand_russell_gap():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_5_"))
    snap = _write_fake_snapshot(tmp, ["russell_norvig_aima"])  # DIFFERENT work present
    cat = _write_catalog(tmp, {
        "russell_norvig_aima": {"author": "Russell & Norvig", "title": "AI: A Modern Approach"},
        "bertrand_russell_the_problems_of_philosophy": {"author": "Bertrand Russell",
                                                         "title": "The Problems of Philosophy"},
    })
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "russell_norvig_aima", "OK", 10)
    _write_sidecar(ext, "bertrand_russell_the_problems_of_philosophy", "OK", 10)
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    stems = {a["stem"] for a in plan["actions"]}
    assert "russell_norvig_aima" not in stems, "present work must be excluded"
    assert "bertrand_russell_the_problems_of_philosophy" in stems, \
        "Bertrand Russell must remain a gap (different work from Russell&Norvig)"


def test_case6_canonical_shannon_present_second_shannon_independent():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_g6_6_"))
    snap = _write_fake_snapshot(tmp, ["claude_shannon_a_mathematical_theory_of_communication"])
    cat = _write_catalog(tmp, {
        "claude_shannon_a_mathematical_theory_of_communication": {
            "author": "Claude Shannon", "title": "A Mathematical Theory of Communication"},
        "shannon_theory_communication": {
            "author": "Claude Shannon", "title": "Theory of Communication (alt source)"},
    })
    ext = tmp / "_extracted"; ext.mkdir(exist_ok=True)
    _write_sidecar(ext, "claude_shannon_a_mathematical_theory_of_communication", "OK", 10)
    _write_sidecar(ext, "shannon_theory_communication", "EXTRACTION_FAILED", 0)
    plan = GapPlanner(snap, cat, extracted_dir=str(ext)).plan()
    stems = {a["stem"] for a in plan["actions"]}
    assert "claude_shannon_a_mathematical_theory_of_communication" not in stems
    assert "shannon_theory_communication" in stems, \
        "second Shannon source is an independent identity, not an alias"
    act = [a for a in plan["actions"] if a["stem"] == "shannon_theory_communication"][0]
    assert act["has_sidecar"] is False, "failed sidecar not actionable"
