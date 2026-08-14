"""STAGE 4 S4.2 — catalog-aware enrichment (ТЗ-KNOWLEDGE-CATALOG-01).

Enrichment reads the catalog YAML and writes legal/section/url into each
graph node's `source`. READ-ONLY on the production snapshot: the test builds a
tiny fake snapshot in a temp dir and verifies enrichment works without ever
touching KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json.

SAFETY: no KROFT_SNAP, no production snapshot read/write. Fully isolated.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.foundation_ingest import enrich_with_catalog  # noqa: E402
from composition.knowledge_persistence import KnowledgeSnapshotStore  # noqa: E402


def _write_catalog(tmp):
    cat = tmp / "catalog.yaml"
    cat.write_text(
        "core_v1:\n"
        "  - author: \"Francis Bacon\"\n"
        "    title: \"Novum Organum\"\n"
        "    section: 02_philosophy\n"
        "    legal: public_domain\n"
        "    url: \"https://example.com/bacon.pdf\"\n"
        "    filename:\n"
        "      - francis_bacon_novum_organum\n",
        encoding="utf-8",
    )
    return str(cat)


def _write_fake_snapshot(tmp):
    snap = tmp / "_snapshot.json"
    payload = {
        "version": 1,
        "graph": {
            "nodes": [
                {
                    "id": "KROFT-FND-francis_bacon_novum_organum-001",
                    "label": "idols",
                    "meta": {
                        "source": {
                            "id": "francis_bacon_novum_organum.pdf",
                            "title": "Novum Organum",
                            "author": "Francis Bacon",
                        }
                    },
                },
                {
                    "id": "KROFT-FND-unknown_book-001",
                    "label": "x",
                    "meta": {"source": {"id": "unknown_book.pdf"}},
                },
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


def test_enrich_adds_catalog_metadata():
    tmp = tempfile.mkdtemp(prefix="kroft_enrich_")
    snap = _write_fake_snapshot(tmp := __import__("pathlib").Path(tmp))
    cat = _write_catalog(tmp)
    out = str(tmp / "enriched.json")

    report = enrich_with_catalog(snap, cat, output_path=out)

    # 1 matched (bacon), 1 missing (unknown_book)
    assert report["matched"] == 1, report
    assert report["total_nodes"] == 2
    assert any("unknown_book" in m for m in report["missing"]), report

    enriched = KnowledgeSnapshotStore(out).load()
    nodes = {n["id"]: n for n in enriched["graph"]["nodes"]}
    bacon = nodes["KROFT-FND-francis_bacon_novum_organum-001"]["meta"]["source"]
    assert bacon["legal"] == "public_domain", bacon
    assert bacon["section"] == "02_philosophy", bacon
    assert bacon["url"] == "https://example.com/bacon.pdf", bacon
    # unknown node left untouched
    unknown = nodes["KROFT-FND-unknown_book-001"]["meta"]["source"]
    assert "legal" not in unknown, unknown


def test_enrich_never_mutates_input_snapshot():
    tmp = tempfile.mkdtemp(prefix="kroft_enrich_ro_")
    tmp_p = __import__("pathlib").Path(tmp)
    snap = _write_fake_snapshot(tmp_p)
    cat = _write_catalog(tmp_p)
    before = open(snap, "rb").read()

    enrich_with_catalog(snap, cat, output_path=str(tmp_p / "enriched.json"))

    after = open(snap, "rb").read()
    assert before == after, "input snapshot must not be mutated"
