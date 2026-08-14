"""Thin adapter: read KROFT-*.md Knowledge Nodes and load them into the
existing KROFT_OS pipeline WITHOUT creating a new engine/graph/storage.

KROFT-*.md (YAML frontmatter)
   -> read_node_file        (stdlib yaml parse)
   -> validated Knowledge Node (dict DTO, no new VO)
   -> InMemoryGraphBuilder  (add_node + add_edge for related/prereq)
   -> ContentIndex          (full-text retrieval over Q+A+tags)
   -> KnowledgeSnapshotStore.save(graph, index, semantic=...)

Constraints honoured (K1/K3/K5/K6/K8):
- services layer imports ONLY contracts / composition / infrastructure / services.
- No new port, no new storage, no new graph, no new retrieval engine.
- Frontmatter is preserved verbatim as the node dict (semantic state).
- Edges to related_concepts / prerequisites are created ONLY when the target
  is a real node.id present in the pilot dataset (no fictional nodes).
- Provenance (source) is stored in meta["source"] and mirrored into tags.

This is a MINIMAL integration seam for the P0 Pilot (84 nodes). Scale-out
(concurrency, streaming, broader edge inference) is out of scope for MVP.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List, Optional

import yaml

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.content_index import ContentIndex
from services.graph_query_engine import GraphQueryEngine
from services.semantic_index import SemanticIndex
from adapters.ollama_embedding import OllamaEmbeddingAdapter
from composition.knowledge_persistence import KnowledgeSnapshotStore


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def read_node_file(path: str) -> Dict[str, Any]:
    """Parse a KROFT-*.md file into a Knowledge Node dict (frontmatter + body)."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        raise ValueError(f"no frontmatter in {path}")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).strip()
    fm["_body"] = body
    fm["_path"] = path
    # KROFT-Q-000123.md -> id from filename (override if frontmatter missing)
    fname = os.path.basename(path)
    if "id" not in fm:
        fm["id"] = fname.rsplit(".", 1)[0]
    return fm


def _node_index_text(node: Dict[str, Any]) -> str:
    parts = [
        node.get("question", ""),
        node.get("answer", ""),
        " ".join(node.get("tags", []) or []),
        " ".join(node.get("related_concepts", []) or []),
    ]
    return " ".join(p for p in parts if p).strip()


def ingest_directory(
    directory: str,
    builder: Optional[InMemoryGraphBuilder] = None,
    index: Optional[ContentIndex] = None,
    store: Optional[KnowledgeSnapshotStore] = None,
    snapshot_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest all KROFT-*.md under ``directory`` into the existing pipeline.

    Returns a summary dict with counts and the assembled engine/store so tests
    can verify retrieval and persistence.
    """
    builder = builder or InMemoryGraphBuilder()
    index = index or ContentIndex()

    files = sorted(glob.glob(os.path.join(directory, "**", "KROFT-*.md"), recursive=True))
    nodes: List[Dict[str, Any]] = []
    read_errors: List[str] = []
    for f in files:
        try:
            nodes.append(read_node_file(f))
        except Exception as exc:  # pragma: no cover - defensive
            read_errors.append(f"{f}: {exc}")

    # First pass: collect valid node ids (targets for edges)
    valid_ids = {n["id"] for n in nodes if "id" in n}
    valid_ids |= {os.path.basename(n["_path"]).rsplit(".", 1)[0] for n in nodes}

    added_nodes = 0
    added_edges = 0
    provenance_missing = 0

    for n in nodes:
        nid = n["id"]
        if not n.get("source") or not n["source"].get("id"):
            provenance_missing += 1
        # meta = everything except the two private keys
        meta = {k: v for k, v in n.items() if k not in ("_body", "_path")}
        # provenance into tags for nodes_by_tag provenance retrieval
        tags = list(meta.get("tags", []) or [])
        src = n.get("source") or {}
        src_id = src.get("id")
        if src_id:
            tags.append(f"source:{src_id}")
        meta["tags"] = tags
        builder.add_node(nid, label=n.get("question", nid), meta=meta)
        added_nodes += 1
        index.index_file(nid, _node_index_text(n))

        # Edges only to real nodes (no fictional targets).
        # related_concepts / prerequisites in the pilot are domain TERM names,
        # not KROFT node-ids, so they do not become graph edges directly.
        # Instead we derive REAL edges that reflect the dataset structure:
        #   (a) same_source      — two nodes sharing a provenance source.id
        #   (b) shares_concept   — two nodes sharing >=1 related_concept term
        # Both connect EXISTING node-ids (no fictional concept nodes), honouring
        # the "no artificial edges / no fictional nodes" constraint.
        pass

    # Second pass: derive edges from provenance + shared concepts (real node-ids).
    by_source: Dict[str, List[str]] = {}
    by_concept: Dict[str, List[str]] = {}
    for n in nodes:
        nid = n["id"]
        src = (n.get("source") or {}).get("id")
        if src:
            by_source.setdefault(src, []).append(nid)
        for rc in n.get("related_concepts", []) or []:
            by_concept.setdefault(rc, []).append(nid)

    def _link(group: List[str], relation: str) -> None:
        nonlocal added_edges
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                # idempotent add_edge; undirected grouping -> both directions
                builder.add_edge(group[i], group[j], relation)
                builder.add_edge(group[j], group[i], relation)
                added_edges += 2

    for src, group in by_source.items():
        if len(group) > 1:
            _link(group, "same_source")
    for rc, group in by_concept.items():
        if len(group) > 1:
            _link(group, "shares_concept")


    # Persist
    if store is not None:
        store.save(
            graph_state=builder.get_graph(),
            index_state=index.snapshot(),
            semantic=[{k: v for k, v in n.items() if k not in ("_body", "_path")} for n in nodes],
            semantic_vectors=semantic_index.snapshot(),
        )

    # Semantic retrieval (PHASE 6B): wire existing SemanticIndex + local Ollama
    # embedding adapter. No new engine/storage/API — GraphQueryEngine already
    # supports semantic_search()/hybrid_search() via RRF. 84 nodes re-indexed
    # on each ingest (cheap; persistence of vectors out of scope per Этап 4).
    semantic_index = SemanticIndex()
    embedding = OllamaEmbeddingAdapter(model="bge-m3")
    for n in nodes:
        nid = n["id"]
        # Variant D document representation (retrieval-quality fix 2026-08-10):
        # enrich the embedded text with source metadata (title, author) and
        # tags so entity-specific queries ("Shannon ...", "Newell/Simon ...")
        # match the right document. Controlled 30-node benchmark proved D
        # beats the old question+answer (Variant B) on Shannon/Newell queries
        # without regressing conceptual ones. bge-m3, chunking, SemanticIndex,
        # GraphQueryEngine and RRF are all unchanged.
        source = n.get("source", {}) or {}
        title = source.get("title", "") or ""
        author = source.get("author", "") or ""
        question = n.get("question", "") or ""
        answer = n.get("answer", "") or ""
        tags = " ".join(n.get("tags", []) or [])
        related_concepts = " ".join(n.get("related_concepts", []) or [])
        vec_text = " ".join(
            part for part in [
                title, author, question, answer, tags, related_concepts,
            ]
            if part
        )
        try:
            semantic_index.add(nid, embedding.embed(vec_text))
        except Exception:
            # embedding server unavailable -> degrade to lexical only (zero regression)
            semantic_index = SemanticIndex()
            embedding = None
            break

    engine = GraphQueryEngine(builder, index=index,
                               semantic_index=semantic_index, embedding=embedding)
    return {
        "builder": builder,
        "index": index,
        "semantic_index": semantic_index,
        "embedding": embedding,
        "engine": engine,
        # PHASE 6E (owner decision): primary retrieval path = hybrid_search.
        # hybrid_search calls SemanticIndex.search directly (correct cosine on
        # bge-m3, R@5=0.90) and fuses with lexical via RRF. It deliberately
        # bypasses the monkey-patched engine.semantic_search (lexical Jaccard),
        # which would otherwise degrade retrieval. GraphQueryEngine / monkey-patch
        # untouched. No new API — composition-layer wiring choice only.
        "primary_retriever": engine.hybrid_search,
        "store": store,
        "nodes": nodes,
        "counts": {
            "files": len(files),
            "read_errors": len(read_errors),
            "added_nodes": added_nodes,
            "added_edges": added_edges,
            "provenance_missing": provenance_missing,
        },
        "snapshot_path": snapshot_path,
    }
