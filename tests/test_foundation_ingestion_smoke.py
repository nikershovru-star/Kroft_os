"""KROFT Knowledge Foundation — self-contained ingestion smoke tests.

Does NOT require Ollama (runs in FORCE_LEXICAL mode). Verifies the parts of the
INGESTION pipeline that are deterministic and Ollama-free:
  1. extraction sidecars exist and are valid JSON with chunks
  2. generated KROFT-FND-*.md nodes parse via the EXISTING read_node_file
     (format compatibility, ТЗ §7)
  3. build() (lexical) builds a GraphQueryEngine and negative queries abstain
     (no hallucination — P0-A)

Writes snapshot to KROFT_SNAP (tmp) so it never touches the live bge-m3 snapshot.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

ROOT = Path(r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS").resolve()
sys_path = str(ROOT)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from composition.knowledge_ingestion import read_node_file  # noqa: E402
from scripts.foundation_ingest import build  # noqa: E402

EXTRACTED = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_extracted"
NODES = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_nodes"


def test_sidecars_valid_and_have_chunks():
    sidecars = sorted(EXTRACTED.glob("*.json"))
    assert sidecars, "no extraction sidecars — run scripts/foundation_extract.py first"
    ok = 0
    for sc in sidecars:
        d = json.loads(sc.read_text(encoding="utf-8"))
        assert "meta" in d
        if d["meta"].get("status") == "OK":
            ok += 1
            assert d.get("chunks"), f"{sc.name} OK but no chunks"
    assert ok >= 20, f"too few extractable PDFs: {ok}"


def test_generated_nodes_parse_with_read_node_file():
    fs = sorted(NODES.glob("KROFT-FND-*.md"))
    assert fs, "no nodes — run scripts/foundation_nodes.py first"
    sampled = fs[:30] + fs[-10:]
    for f in sampled:
        n = read_node_file(f)
        assert n.get("question"), f"{f.name} missing question"
        assert n.get("answer"), f"{f.name} missing answer"
        assert n.get("source", {}).get("page_start") is not None, f"{f.name} missing page_start"


def test_build_lexical_engine_and_negative_abstention():
    os.environ["FORCE_LEXICAL"] = "1"
    tmp = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_snapshot_test.json"
    os.environ["KROFT_SNAP"] = str(tmp)
    try:
        res = build()
        engine = res["engine"]
        assert res["node_count"] > 1000
        assert res["embedding"] is None  # lexical-only
        # negative query must abstain (no hallucination)
        findings, ab = engine.query_with_abstention(
            "How does a quantum flux capacitor engine work?", semantic_threshold=0.30)
        assert ab or len(findings) == 0, "negative query should abstain"
    finally:
        os.environ.pop("FORCE_LEXICAL", None)
        os.environ.pop("KROFT_SNAP", None)
        if tmp.exists():
            tmp.unlink()
