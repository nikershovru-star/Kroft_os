"""ТЗ-KNOWLEDGE-ENGINE-01 (ADR-091) — Knowledge Engine K8 tests (Флаг 1b, separate).

Covers: ingest grows graph (nodes/edges); relations from [[wikilinks]]; backlinks (reverse
edges); determinism (I-09, LLM-free); LLM-free works without advisor; duplicate ingest is
idempotent (no duplicate nodes/edges). K5: reuses IKnowledgeEngine/KnowledgeExtraction,
InMemoryGraphEngine, Node/Edge/NodeType/EdgeType, IEntityExtractor (optional). No existing
graph/search/research ports duplicated.
"""

from __future__ import annotations

from typing import Optional

import pytest

from contracts.i_knowledge import Entity, Fact, Relation
from contracts.i_knowledge_engine import IKnowledgeEngine, KnowledgeExtraction
from contracts.knowledge_graph import EdgeType, NodeType

from services.knowledge_graph.engine import InMemoryGraphEngine
from services.knowledge_engine import KnowledgeEngine, build_knowledge_engine
from composition.knowledge_engine_factory import build_default_engine, ingest_file


DOC = "# My Note\n\nThis links to [[Target A]] and [[Target B]].\n# Section Two\n\nDone."


def _engine(graph=None):
    g = graph or InMemoryGraphEngine()
    return build_knowledge_engine(g), g


def test_knowledge_engine_implements_port():
    eng, _ = _engine()
    assert isinstance(eng, IKnowledgeEngine)


def test_ingest_grows_graph():
    eng, g = _engine()
    r = eng.ingest("doc1", DOC)
    assert isinstance(r, KnowledgeExtraction)
    # doc1 + 2 wikilink targets + 2 header entities = nodes created
    assert len(g._nodes) >= 3
    # each wikilink -> 2 edges (REFERENCES + BACKLINKS)
    assert len(r.relations) == 2
    total_edges = sum(len(v) for v in g._out.values())
    assert total_edges == 4  # 2 links * 2 directions


def test_relations_from_wikilinks():
    eng, _ = _engine()
    r = eng.ingest("doc1", DOC)
    rel_objects = {rel.object for rel in r.relations}
    assert "Target A" in rel_objects
    assert "Target B" in rel_objects
    assert all(rel.predicate == "links" for rel in r.relations)


def test_backlinks_created():
    eng, g = _engine()
    eng.ingest("doc1", DOC)
    # doc1 -> Target A (REFERENCES) AND Target A -> doc1 (BACKLINKS)
    out_doc1 = g._out["doc1"]
    out_ta = g._out["Target A"]
    assert any(e.target_id == "Target A" and e.type == EdgeType.REFERENCES for e in out_doc1)
    assert any(e.target_id == "doc1" and e.type == EdgeType.BACKLINKS for e in out_ta)


def test_determinism():
    """Same doc -> identical extraction (I-09, LLM-free)."""
    a = build_knowledge_engine(InMemoryGraphEngine()).ingest("d", DOC)
    b = build_knowledge_engine(InMemoryGraphEngine()).ingest("d", DOC)
    assert a.entities == b.entities
    assert a.relations == b.relations
    assert a.facts == b.facts


def test_llm_free_works_without_advisor():
    """No extractor -> heuristic extraction still returns entities/relations/facts."""
    eng, _ = _engine()
    r = eng.ingest("doc1", DOC)
    assert len(r.entities) >= 1
    assert len(r.relations) == 2
    assert len(r.facts) == 2


def test_duplicate_ingest_idempotent():
    """Re-ingesting the same doc does NOT create duplicate nodes/edges."""
    eng, g = _engine()
    eng.ingest("doc1", DOC)
    nodes_after_first = len(g._nodes)
    edges_after_first = sum(len(v) for v in g._out.values())
    r2 = eng.ingest("doc1", DOC)
    assert len(g._nodes) == nodes_after_first
    assert sum(len(v) for v in g._out.values()) == edges_after_first
    assert len(r2.relations) == 2  # extraction is reproducible, not duplicated in graph


def test_malformed_doc_returns_empty_not_crash():
    """O1: empty/garbage input -> empty extraction, no raise."""
    eng, g = _engine()
    r = eng.ingest("empty", "")
    assert isinstance(r, KnowledgeExtraction)
    assert r.entities == () and r.relations == () and r.facts == ()
    # doc node still created (idempotent ensure), graph did not explode
    assert len(g._nodes) == 1


def test_ingest_file_stdlib_no_sdk(tmp_path):
    """Obsidian-source file read via stdlib (composition), no SDK import."""
    f = tmp_path / "note.md"
    f.write_text(DOC, encoding="utf-8")
    eng = build_default_engine(InMemoryGraphEngine())
    r = ingest_file(eng, str(f))
    assert isinstance(r, KnowledgeExtraction)
    assert len(r.relations) == 2
    assert "note" in eng._graph.get_node("note").id  # doc_id = file stem


def test_optional_llm_extractor_enriches():
    """Optional IEntityExtractor advisor enriches extraction; failure falls back."""
    class FakeExtractor:
        def extract(self, text, context):
            return [Entity(name="x", type="concept")]
        def extract_relations(self, text, context):
            from contracts.i_knowledge import Hypothesis
            return [Hypothesis(subject="s", predicate="p", object="o", confidence=0.9)]
    eng = build_knowledge_engine(InMemoryGraphEngine(), extractor=FakeExtractor())
    r = eng.ingest("doc1", DOC)
    # heuristic (2 relations) + advisor (1 relation) = 3
    assert len(r.relations) == 3
    assert any(rel.subject == "s" for rel in r.relations)
