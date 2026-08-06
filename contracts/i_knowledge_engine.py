"""Knowledge Engine port — document ingestion -> knowledge extraction (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091).

K1-compliant: stdlib + contracts only. K5: this is a NEW orchestration seam (ingest a document
-> extract entities/relations/facts -> update the graph + content index). It does NOT duplicate
existing ports:
  - contracts/i_knowledge.py already has IEntityExtractor (LLM-based entity/relation extraction),
    IKnowledgeGraph (Facts storage), and the Entity/Relation/Hypothesis/Fact/IngestReport VOs.
    We REUSE Entity/Relation/Fact (import, never redefine).
  - contracts/knowledge_graph.py already has IGraphEngine + Node/Edge/NodeType/EdgeType.
    We REUSE them (the engine writes through IGraphEngine).
The missing piece was the ingest orchestration boundary itself -> IKnowledgeEngine is that seam.

Determinism (I-09): the reference impl extracts via LLM-free heuristics (regex + [[wikilink]])
by default, so ingestion is reproducible without a model. A live LLM advisor (IEntityExtractor)
is OPTIONAL and only enriches extraction; failures fall back to the heuristic path (retrieval-only).
O1: ingestion never crashes the kernel; malformed docs yield an empty extraction, not an error.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Tuple

from contracts.i_knowledge import Entity, Fact, Relation


@dataclass(frozen=True)
class KnowledgeExtraction:
    """Frozen result of ingesting one document (ТЗ-KNOWLEDGE-ENGINE-01).

    Reuses the existing i_knowledge VOs (Entity/Relation/Fact) — no redefinition. Frozen
    like IngestReport's siblings so an ingest is data, not a side effect.
    """

    entities: Tuple[Entity, ...] = ()
    relations: Tuple[Relation, ...] = ()
    facts: Tuple[Fact, ...] = ()


class IKnowledgeEngine(ABC):
    """Port: ingest a document and return extracted knowledge (ТЗ-KNOWLEDGE-ENGINE-01).

    Contract:
      - ``ingest(doc_id, text)`` parses ``text`` (markdown/obsidian), extracts entities,
        relations (incl. [[wikilink]] backlinks) and facts, and returns a frozen
        KnowledgeExtraction. The engine updates the injected IGraphEngine + content index.
      - Deterministic (I-09) when LLM-free: same doc -> same extraction + same graph delta.
      - On malformed input MUST return an empty KnowledgeExtraction, NOT raise (O1).
      - MUST NOT import a provider SDK; document reading is stdlib file I/O (composition layer).
    """

    @abstractmethod
    def ingest(self, doc_id: str, text: str) -> KnowledgeExtraction:
        """Ingest ``text`` as document ``doc_id``; return extracted knowledge."""
        raise NotImplementedError
