"""KnowledgeEngine — document ingestion -> knowledge extraction (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091).

K6: lives in services/ — imports ONLY contracts (i_knowledge_engine, i_knowledge, knowledge_graph).
The graph engine + content index are INJECTED (never imported concrete), so this module stays
axis-clean (services -> contracts only). Optionally accepts an LLM-based IEntityExtractor for
richer extraction; failures fall back to the LLM-free heuristic (retrieval-only, O1).

Behaviour (ТЗ-KNOWLEDGE-ENGINE-01):
  read -> extract -> link -> update graph -> new links (backlinks).
  - LLM-free by default (I-09): deterministic regex + [[wikilink]] parsing.
  - entities: markdown # headers + [[wikilink]] targets.
  - relations: each [[wikilink]] -> doc links target; reverse BACKLINKS edge created too.
  - facts: LLM-free relations promoted to Facts (confidence 1.0, source=doc_id).
  - idempotent: get_node() check before add_node; add_edge() is itself idempotent.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from contracts.i_knowledge import Entity, Fact, Relation
from contracts.i_knowledge_engine import IKnowledgeEngine, KnowledgeExtraction
from contracts.knowledge_graph import (
    Edge,
    EdgeType,
    IGraphEngine,
    Node,
    NodeType,
)

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_HEADER_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)


class KnowledgeEngine(IKnowledgeEngine):
    """Reference Knowledge Engine: ingest a document into the graph (ТЗ-KNOWLEDGE-ENGINE-01)."""

    def __init__(self, graph: IGraphEngine,
                 content_index=None,
                 extractor=None) -> None:
        # graph + content_index + extractor are INJECTED (composition root supplies the
        # concrete InMemoryGraphEngine / ContentIndex / IEntityExtractor). K6: no concrete
        # services imported here.
        self._graph = graph
        self._content_index = content_index
        self._extractor = extractor  # optional IEntityExtractor (LLM advisor)

    def ingest(self, doc_id: str, text: str) -> KnowledgeExtraction:
        text = text or ""
        entities: List[Entity] = []
        relations: List[Relation] = []
        facts: List[Fact] = []

        # --- LLM-free heuristic extraction (deterministic, I-09) ----------------
        # entities: markdown headers + wikilink targets
        headers = [h.strip() for h in _HEADER_RE.findall(text)]
        for h in headers:
            entities.append(Entity(name=h, type="concept", source=doc_id))
        targets = [t.strip() for t in _WIKILINK_RE.findall(text)]
        for t in targets:
            entities.append(Entity(name=t, type="note", source=doc_id))
            # relation: doc links target
            rel = Relation(subject=doc_id, predicate="links", object=t)
            relations.append(rel)
            facts.append(Fact(subject=doc_id, predicate="links", object=t,
                              source=doc_id, confidence=1.0))

        # --- optional LLM advisor (non-blocking: fall back on failure) --------
        if self._extractor is not None:
            try:
                extra_rels = self._extractor.extract_relations(text, None)
                for hyp in extra_rels:
                    if hyp.is_well_formed():
                        relations.append(hyp.as_relation())
                        facts.append(Fact(
                            subject=hyp.subject, predicate=hyp.predicate,
                            object=hyp.object, source=hyp.source or doc_id,
                            confidence=hyp.confidence,
                        ))
            except Exception:
                pass  # advisor failure -> keep heuristic extraction (retrieval-only)

        # --- update graph (idempotent) ----------------------------------------
        self._ensure_node(doc_id, NodeType.NOTE)
        for ent in entities:
            self._ensure_node(ent.name, NodeType.NOTE)
        for rel in relations:
            self._ensure_node(rel.subject, NodeType.NOTE)
            self._ensure_node(rel.object, NodeType.NOTE)
            self._graph.add_edge(Edge(rel.subject, rel.object, EdgeType.REFERENCES))
            # backlink: reverse edge so the target knows it is referenced
            self._graph.add_edge(Edge(rel.object, rel.subject, EdgeType.BACKLINKS))

        # --- content index ----------------------------------------------------
        if self._content_index is not None:
            try:
                self._content_index.index_file(doc_id, text)
            except Exception:
                pass  # indexing is best-effort; extraction still returned

        return KnowledgeExtraction(
            entities=tuple(entities),
            relations=tuple(relations),
            facts=tuple(facts),
        )

    def _ensure_node(self, node_id: str, ntype: NodeType) -> None:
        """Idempotent node creation: skip if already present (no duplicates)."""
        if self._graph.get_node(node_id) is None:
            self._graph.add_node(Node(id=node_id, type=ntype, label=node_id))


def build_knowledge_engine(graph: IGraphEngine,
                            content_index=None,
                            extractor=None) -> "KnowledgeEngine":
    """Standalone factory (Флаг C) — wire a KnowledgeEngine over injected ports.

    The graph engine + content index + optional LLM extractor are supplied by the caller
    (composition root), never imported here (K6: services -> contracts only).
    """
    return KnowledgeEngine(graph=graph, content_index=content_index, extractor=extractor)
