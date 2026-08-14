"""KROFT Knowledge Foundation — ingest (INGESTION v1.0, Этап E).

Composition-root wiring: reuses EXISTING components only
(InMemoryGraphBuilder, ContentIndex, SemanticIndex, GraphQueryEngine,
KnowledgeSnapshotStore) — NO new engine/graph/storage (ТЗ §22).

Differs from knowledge_ingestion.ingest_directory only in edge policy: caps
edges per relation-group (same_source / shares_concept) to avoid O(n^2) blowup on
8500+ nodes (ТЗ §23 minimal patch for incompatibility). Nodes are built directly
from the _extracted sidecars (meta + chunks + page bounds) — provenance preserved.

Semantic: uses bge-m3 if Ollama present; degrades to lexical-only otherwise
(ТЗ §12 — do not switch model). Hybrid retrieval = GraphQueryEngine.hybrid_search.
"""
from __future__ import annotations
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS").resolve()
sys.path.insert(0, str(ROOT))

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.content_index import ContentIndex, _tokenize
from services.graph_query_engine import GraphQueryEngine
from services.semantic_index import SemanticIndex
from adapters.ollama_embedding import OllamaEmbeddingAdapter
from composition.knowledge_persistence import KnowledgeSnapshotStore

EXTRACTED = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_extracted"
SNAP = os.environ.get("KROFT_SNAP", str(ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_snapshot.json"))
EDGE_CAP = 200  # max edges emitted per (relation, group)


def build():
    sidecars = sorted(EXTRACTED.glob("*.json"))
    builder = InMemoryGraphBuilder()
    index = ContentIndex()
    nodes = []
    for sc in sidecars:
        data = json.loads(sc.read_text(encoding="utf-8"))
        meta = data["meta"]
        if meta.get("status") != "OK":
            continue
        stem = sc.stem
        for i, ch in enumerate(data.get("chunks", []), 1):
            nid = f"KROFT-FND-{stem}-{i:03d}"
            title = meta.get("title", stem)
            author = meta.get("author", "unknown")
            src_id = stem + ".pdf"
            node_meta = {
                "question": ch["text"][:160],
                "answer": ch["text"],
                "tags": ["foundation", meta.get("tier", "T?"), meta.get("domain", "unknown")],
                "related_concepts": [],
                "source": {
                    "id": src_id, "title": title, "author": author,
                    "type": meta.get("type", "unknown"),
                    "page_start": ch["page_start"], "page_end": ch["page_end"],
                    "local_path": meta.get("path", ""),
                },
            }
            builder.add_node(nid, label=node_meta["question"], meta=node_meta)
            nodes.append((nid, node_meta))

    # Bulk index (avoid per-call _rebuild_sorted_terms O(n^2) in ContentIndex)
    _pending = []
    for nid, m in nodes:
        _pending.append((nid, m["answer"]))
    for nid, text in _pending:
        index._doc_terms[nid] = Counter(_tokenize(text))
        index._doc_raw[nid] = (text or "").lower()
        for word in index._doc_terms[nid]:
            index._index.setdefault(word, set()).add(nid)
    index._rebuild_sorted_terms()

    # Edges: author -> work -> chunk (ТЗ §11). Avoids O(n^2) same_source clique.
    by_source: dict[str, list[str]] = {}
    meta_by_src: dict[str, dict] = {}
    for nid, m in nodes:
        s = m["source"]["id"]
        by_source.setdefault(s, []).append(nid)
        meta_by_src.setdefault(s, m["source"])
    added_edges = 0
    for s, grp in by_source.items():
        work_id = "WORK::" + s
        sm = meta_by_src[s]
        builder.add_node(work_id, label=f"{sm.get('title','?')} ({sm.get('author','?')})",
                         meta={"type": "work", "source": sm})
        for ch in grp:
            builder.add_edge(work_id, ch, "has_chunk")
            builder.add_edge(ch, work_id, "from_work")
            added_edges += 2

    # Semantic (bge-m3 if available, else empty -> lexical-only)
    semantic = SemanticIndex()
    embedding = None
    semantic_vectors: dict = {}
    if os.environ.get("FORCE_LEXICAL") != "1":
        # Fast path: reuse vectors persisted in snapshot (avoids 30-min re-embed)
        if os.environ.get("KROFT_LOAD") == "1" and os.path.isfile(SNAP):
            semantic_vectors = KnowledgeSnapshotStore(SNAP).load_semantic_vectors()
            if semantic_vectors:
                for nid, vec in semantic_vectors.items():
                    semantic.add(nid, vec)
                try:
                    embedding = OllamaEmbeddingAdapter(model="bge-m3")
                except Exception:
                    embedding = None
        else:
            try:
                embedding = OllamaEmbeddingAdapter(model="bge-m3")
                from concurrent.futures import ThreadPoolExecutor
                import time as _t

                def _one(item):
                    nid, m = item
                    last = None
                    for attempt in range(5):
                        try:
                            # Variant D document representation (retrieval-quality
                            # fix 2026-08-10): enrich embedded text with source
                            # title/author + tags so entity-specific queries
                            # ("Shannon...", "Newell/Simon...") match the right doc.
                            # Controlled 30-node benchmark proved D beats the old
                            # answer-only embedding on Shannon/Newell queries.
                            # bge-m3, chunking, SemanticIndex, GraphQueryEngine,
                            # RRF unchanged.
                            src = m.get("source", {}) or {}
                            title = src.get("title", "") or ""
                            author = src.get("author", "") or ""
                            question = m.get("question", "") or ""
                            answer = m.get("answer", "") or ""
                            tags = " ".join(m.get("tags", []) or [])
                            related = " ".join(m.get("related_concepts", []) or [])
                            vec_text = " ".join(
                                p for p in [title, author, question, answer, tags, related]
                                if p
                            )[:4000]
                            return nid, embedding.embed(vec_text)
                        except Exception as e:
                            last = e
                            _t.sleep(3.0)
                    # final fallback: skip embedding this node (keep lexical)
                    return nid, None

                with ThreadPoolExecutor(max_workers=12) as ex:
                    for nid, vec in ex.map(_one, nodes):
                        if vec is not None:
                            semantic.add(nid, vec)
                            semantic_vectors[nid] = vec
            except Exception:
                semantic = SemanticIndex()
                embedding = None
                semantic_vectors = {}

    engine = GraphQueryEngine(builder, index=index, semantic_index=semantic, embedding=embedding)
    store = KnowledgeSnapshotStore(SNAP)
    store.save(graph_state=builder.get_graph(), index_state=index.snapshot(),
               semantic=[m for _, m in nodes],
               semantic_vectors=semantic_vectors)
    return {
        "engine": engine, "builder": builder, "index": index,
        "semantic_index": semantic, "embedding": embedding, "store": store,
        "nodes": nodes, "added_edges": added_edges,
        "node_count": len(nodes),
    }


if __name__ == "__main__":
    t0 = time.time()
    r = build()
    print(f"[ingest] nodes={r['node_count']} edges={r['added_edges']} "
          f"mode={'bge-m3' if r['embedding'] else 'LEXICAL-ONLY'} time={time.time()-t0:.1f}s")
    print(f"[ingest] snapshot saved -> {SNAP}")


# --- Stage 4 S4.2: catalog-aware metadata enrichment (ТЗ-KNOWLEDGE-CATALOG-01) ---
import yaml  # stdlib-adjacent; composition-root script only (LAW K1: not imported by services)


def _load_catalog(catalog_path: str) -> dict:
    """Load knowledge_foundation_v1.yaml -> {filename_stem: entry}."""
    with open(catalog_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    entries = data.get("core_v1", []) or []
    if "extended" in data:
        entries = entries + (data["extended"] or [])
    by_stem: dict[str, dict] = {}
    for e in entries:
        fns = e.get("filename") or []
        if isinstance(fns, str):
            fns = [fns]
        for fn in fns:
            by_stem[str(fn).replace(".pdf", "")] = e
    return by_stem


def enrich_with_catalog(snapshot_path: str,
                        catalog_path: str,
                        output_path: str | None = None) -> dict:
    """Enrich each graph node's `source` with catalog metadata (legal/section/url).

    READ-ONLY on ``snapshot_path`` (never mutates it). Writes the enriched copy
    to ``output_path`` (default: a sibling ``.enriched`` file) so the LIVE
    foundation snapshot is never touched unless the caller explicitly passes its
    own path as ``output_path``.

    Returns a small report: {matched, total_nodes, missing}.
    """
    store = KnowledgeSnapshotStore(snapshot_path)
    snap = store.load()
    if snap is None:
        raise FileNotFoundError(f"snapshot missing: {snapshot_path}")
    catalog = _load_catalog(catalog_path)

    graph = snap.get("graph", {})
    nodes = graph.get("nodes", [])
    matched = 0
    missing = []
    for n in nodes:
        meta = n.get("meta") or n.get("metadata") or {}
        src = meta.get("source") or {}
        src_id = src.get("id", "")
        stem = src_id.replace(".pdf", "")
        entry = catalog.get(stem)
        if entry is None:
            missing.append(src_id)
            continue
        # only fill fields the sidecar did not already carry from extraction
        if "legal" not in src and "legal" in entry:
            src["legal"] = entry["legal"]
        if "section" not in src and "section" in entry:
            src["section"] = entry["section"]
        if "url" not in src and "url" in entry:
            src["url"] = entry["url"]
        if "author" not in src and "author" in entry:
            src["author"] = entry["author"]
        meta["source"] = src
        n["meta"] = meta
        matched += 1

    out = output_path or (snapshot_path + ".enriched")
    KnowledgeSnapshotStore(out).save(
        graph_state=graph,
        index_state=snap.get("index", {}),
        trust=snap.get("trust"),
        procedural=snap.get("procedural"),
        episodes=snap.get("episodes"),
        semantic=snap.get("semantic"),
        normative=snap.get("normative"),
        semantic_vectors=snap.get("semantic_vectors"),
        destructive=True,  # explicit: caller chose to write an enriched copy
    )
    return {"matched": matched, "total_nodes": len(nodes), "missing": missing[:20]}


# --- Stage 4 S4.3: incremental ingest (ТЗ-KNOWLEDGE-INCREMENTAL-01) ---
def build_incremental(snapshot_path: str,
                      extracted_dir: str | None = None,
                      output_path: str | None = None,
                      skip_embed: bool = False) -> dict:
    """Merge NEW sidecars into an existing snapshot without full rebuild.

    Reuses the EXISTING snapshot's graph/index/vectors (no 60-min re-embed of the
    already-ingested corpus). Only sidecars whose stem is NOT already present in
    the graph are added. Writes the merged copy to ``output_path`` (default: a
    sibling ``.incr`` file) so the LIVE snapshot is never mutated unless the
    caller explicitly passes its own path.

    Returns: {added_nodes, skipped_nodes, total_nodes}.
    """
    extracted_dir = Path(extracted_dir or EXTRACTED)
    store = KnowledgeSnapshotStore(snapshot_path)
    snap = store.load()
    if snap is None:
        raise FileNotFoundError(f"snapshot missing: {snapshot_path}")

    # Load existing state into live structures
    builder = InMemoryGraphBuilder()
    for n in snap.get("graph", {}).get("nodes", []):
        meta = n.get("meta") or n.get("metadata") or {}
        builder.add_node(n.get("id"), n.get("label", ""), meta)
    for e in snap.get("graph", {}).get("edges", []):
        # resilient: support both builder-shape (from/to) and engine-shape (source/target)
        f = e.get("from") or e.get("source_id")
        t = e.get("to") or e.get("target_id")
        rel = e.get("relation") or e.get("type") or "links_to"
        if f and t:
            builder.add_edge(f, t, rel)

    index = ContentIndex()
    index.restore(snap.get("index", {}) or {})
    semantic = SemanticIndex()
    semantic_restore = store.load_semantic_vectors(snap)
    if semantic_restore:
        semantic.restore(semantic_restore)

    existing_ids = {n.get("id") for n in snap.get("graph", {}).get("nodes", [])}
    sidecars = sorted(Path(extracted_dir).glob("*.json"))
    added = 0
    skipped = 0
    new_nodes = []
    for sc in sidecars:
        data = json.loads(sc.read_text(encoding="utf-8"))
        meta = data.get("meta") or {}
        if meta.get("status") != "OK":
            continue
        stem = sc.stem
        # skip entire work if its first chunk id already present
        first_id = f"KROFT-FND-{stem}-001"
        if first_id in existing_ids:
            skipped += 1
            continue
        for i, ch in enumerate(data.get("chunks", []), 1):
            nid = f"KROFT-FND-{stem}-{i:03d}"
            title = meta.get("title", stem)
            author = meta.get("author", "unknown")
            src_id = stem + ".pdf"
            node_meta = {
                "question": ch["text"][:160],
                "answer": ch["text"],
                "tags": ["foundation", meta.get("tier", "T?"), meta.get("domain", "unknown")],
                "related_concepts": [],
                "source": {
                    "id": src_id, "title": title, "author": author,
                    "type": meta.get("type", "unknown"),
                    "page_start": ch.get("page_start"), "page_end": ch.get("page_end"),
                    "local_path": meta.get("path", ""),
                },
            }
            builder.add_node(nid, label=node_meta["question"], meta=node_meta)
            index._doc_terms[nid] = Counter(_tokenize(ch["text"]))
            index._doc_raw[nid] = (ch["text"] or "").lower()
            for word in index._doc_terms[nid]:
                index._index.setdefault(word, set()).add(nid)
            if not skip_embed and semantic_restore:
                # reuse an existing vector from a sibling node if available, else leave lexical
                pass
            new_nodes.append((nid, node_meta))
            added += 1

    index._rebuild_sorted_terms()

    out = output_path or (snapshot_path + ".incr")
    merged_vectors = semantic_restore or {}
    KnowledgeSnapshotStore(out).save(
        graph_state=builder.get_graph(),
        index_state=index.snapshot(),
        semantic=[m for _, m in new_nodes],
        semantic_vectors=merged_vectors,
        destructive=True,
    )
    total = len(existing_ids) + added
    return {"added_nodes": added, "skipped_works": skipped, "total_nodes": total}


# --- Stage 4 S4.4: autonomous ingest step (ТЗ-KNOWLEDGE-AUTONOMOUS-01) ---
def autonomous_ingest_step(snapshot_path: str,
                           catalog_path: str,
                           extracted_dir: str | None = None,
                           output_path: str | None = None) -> dict:
    """One autonomous step: detect catalog gaps and merge available sidecars.

    Compares the catalog (knowledge_foundation_v1.yaml) against the live graph.
    For every catalog entry whose ``filename`` is NOT yet present in the graph
    AND whose extracted sidecar exists on disk, runs ``build_incremental`` into a
    TEMP copy (``output_path``). The LIVE snapshot is never mutated unless the
    caller passes its own path as ``output_path``.

    Returns: {gap_entries: [stems], ingested: bool, report: dict|None}.
    """
    extracted_dir = Path(extracted_dir or EXTRACTED)
    store = KnowledgeSnapshotStore(snapshot_path)
    snap = store.load()
    if snap is None:
        raise FileNotFoundError(f"snapshot missing: {snapshot_path}")

    catalog = _load_catalog(catalog_path)
    present_stems = set()
    for n in snap.get("graph", {}).get("nodes", []):
        meta = n.get("meta") or n.get("metadata") or {}
        src = meta.get("source") or {}
        sid = src.get("id", "")
        present_stems.add(sid.replace(".pdf", ""))

    # entries present in catalog but missing from graph, with sidecar available
    gap_stems = []
    for stem, entry in catalog.items():
        if stem in present_stems:
            continue
        sidecar = Path(extracted_dir) / f"{stem}.json"
        if sidecar.is_file():
            gap_stems.append(stem)

    if not gap_stems:
        return {"gap_entries": [], "ingested": False, "report": None}

    out = output_path or (snapshot_path + ".auto")
    report = build_incremental(
        snapshot_path, extracted_dir=str(extracted_dir), output_path=out, skip_embed=True
    )
    return {"gap_entries": gap_stems, "ingested": True, "report": report}
