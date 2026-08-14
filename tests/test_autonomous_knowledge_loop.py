"""Autonomous Knowledge Loop integration (ТЗ-KNOWLEDGE-AUTONOMOUS-LOOP-01).

Connects ResearchAgent (gap_detected) -> GapPlanner -> autonomous_ingest_step.
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

from composition.autonomous_knowledge_loop import AutonomousKnowledgeLoop  # noqa: E402
from composition.knowledge_persistence import KnowledgeSnapshotStore  # noqa: E402
from services.research_agent import ResearchAgent  # noqa: E402
from contracts.i_search import ISearchService, SearchHit, SearchScope, ConfidenceScore  # noqa: E402


class _FakeSearch(ISearchService):
    """Returns 0 hits -> forces ResearchAgent to signal a KNOWLEDGE_GAP."""
    def search(self, query: str, scope: SearchScope = SearchScope.ALL,
               top_k: int = 5):  # type: ignore[override]
        return []


def _hit(source: str, content: str) -> SearchHit:
    return SearchHit(
        content=content, source=source, hit_type="graph",
        confidence=ConfidenceScore(0.9), causal=None, relevance=1.0,
    )


def _write_fake_snapshot(tmp: Path) -> str:
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


def _write_catalog(tmp: Path) -> str:
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


def _write_wiener_sidecar(tmp: Path) -> str:
    ext = tmp / "_extracted"
    ext.mkdir(exist_ok=True)
    (ext / "norbert_wiener_cybernetics.json").write_text(json.dumps({
        "meta": {"status": "OK", "title": "Cybernetics", "author": "Norbert Wiener"},
        "chunks": [{"text": "cybernetics control", "page_start": 1, "page_end": 1}],
    }), encoding="utf-8")
    return str(ext)


def test_self_heal_detects_gap_and_ingests_to_temp():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_loop_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)

    agent = ResearchAgent(search=_FakeSearch(), llm=None, top_k=5)
    loop = AutonomousKnowledgeLoop(agent, snap, catalog_path=cat, extracted_dir=ext)

    report = loop.self_heal("cybernetics control theory")
    assert report["gap_detected"] is True, report
    assert report["ingested"] is True, report
    assert report["output_path"] is not None
    assert report["plan"]["actionable"] >= 1, report

    # the merged TEMP copy contains the new node
    merged = KnowledgeSnapshotStore(report["output_path"]).load()
    ids = {n["id"] for n in merged["graph"]["nodes"]}
    assert "KROFT-FND-norbert_wiener_cybernetics-001" in ids
    # original live snapshot preserved
    assert "KROFT-FND-francis_bacon_novum_organum-001" in {n["id"] for n in
           KnowledgeSnapshotStore(snap).load()["graph"]["nodes"]}


def test_self_heal_no_gap_is_noop():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_loop_nogap_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)

    # a search that returns hits -> no gap
    class _HitSearch(ISearchService):
        def search(self, query: str, scope: SearchScope = SearchScope.ALL,
                   top_k: int = 5):  # type: ignore[override]
            return [_hit("francis_bacon_novum_organum.pdf", "idols of the mind")]

    agent = ResearchAgent(search=_HitSearch(), llm=None, top_k=5)
    loop = AutonomousKnowledgeLoop(agent, snap, catalog_path=cat, extracted_dir=ext)

    report = loop.self_heal("idols of the mind")
    assert report["gap_detected"] is False, report
    assert report["ingested"] is False
    assert report["output_path"] is None


def test_self_heal_never_mutates_live_snapshot():
    tmp = Path(tempfile.mkdtemp(prefix="kroft_loop_ro_"))
    snap = _write_fake_snapshot(tmp)
    cat = _write_catalog(tmp)
    ext = _write_wiener_sidecar(tmp)
    before = open(snap, "rb").read()

    agent = ResearchAgent(search=_FakeSearch(), llm=None, top_k=5)
    loop = AutonomousKnowledgeLoop(agent, snap, catalog_path=cat, extracted_dir=ext)
    loop.self_heal("cybernetics control theory")

    assert open(snap, "rb").read() == before, "live snapshot must not be mutated"
