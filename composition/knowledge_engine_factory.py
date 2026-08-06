"""Knowledge Engine composition (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091, Флаг C).

Standalone wiring + Obsidian-source file reader (stdlib only, NO Obsidian SDK). Composition
root may import contracts + services + adapters (gate rule: composition -> everything), so
this module reads a markdown file from disk and feeds it to a KnowledgeEngine. K6-clean:
the engine itself (services/knowledge_engine.py) never touches the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from contracts.i_knowledge_engine import IKnowledgeEngine, KnowledgeExtraction
from contracts.knowledge_graph import IGraphEngine
from services.knowledge_engine import KnowledgeEngine, build_knowledge_engine


def build_default_engine(graph: IGraphEngine, content_index=None,
                         extractor=None) -> KnowledgeEngine:
    """Build a KnowledgeEngine over the injected graph (Флаг C)."""
    return build_knowledge_engine(graph=graph, content_index=content_index, extractor=extractor)


def ingest_file(engine: IKnowledgeEngine, path: str,
                doc_id: Optional[str] = None) -> KnowledgeExtraction:
    """Ingest a markdown/Obsidian file from disk (stdlib read, NO SDK).

    doc_id defaults to the file stem. Returns the extraction; the engine has already
    updated the injected graph + content index.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    did = doc_id or p.stem
    return engine.ingest(did, text)
