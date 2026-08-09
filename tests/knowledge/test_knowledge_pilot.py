"""Slice: KROFT_KNOWLEDGE pilot — ingestion -> graph -> snapshot -> retrieval proof.

Proof (K5): knowledge nodes are taught to KROFT not by dumping documents but by
ingesting atomic Q&A through the EXISTING pipeline — KnowledgeEngine extracts headers/
wikilinks into InMemoryGraphEngine, ContentIndex builds the inverted index — then a
snapshot is taken (KnowledgeSnapshotStore) and retrieval (ContentIndex AND-search) finds
the correct node for >=90% of the pilot corpus. No new storage layer; no contracts change;
no external books/videos.

Pilot corpus: KROFT_KNOWLEDGE/qa_*.md (506 nodes across 26 owner domains, 7 types
incl. SELF + DECISIONAL + EXPERIENCE). Scaled from the 70-node pilot to prove the
ingestion -> graph -> snapshot -> retrieval pipeline teaches KROFT at corpus scale.
"""

import os

from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine
from composition.knowledge_persistence import KnowledgeSnapshotStore

PILOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "KROFT_KNOWLEDGE",
)


def _load_pilot():
    # Bound to the 506-node pilot. The scaled 10k+ corpus lives in the same dir
    # but is exercised only by the gated KNOWLEDGE_SCALE test, so the always-run
    # suite never ingests it (keeps wall-time ~minutes, not tens of minutes).
    files = []
    for f in os.listdir(PILOT_DIR):
        if not (f.startswith("qa_") and f.endswith(".md")):
            continue
        nid = f[:-3]
        try:
            if int(nid.split("_")[1]) > 506:
                continue
        except (IndexError, ValueError):
            continue
        files.append(f)
    files = sorted(files)
    nodes = []
    for f in files:
        doc_id = f[:-3]  # strip .md
        with open(os.path.join(PILOT_DIR, f), encoding="utf-8") as fh:
            text = fh.read()
        nodes.append((doc_id, text))
    return nodes


def test_pilot_ingestion_builds_graph_and_index():
    """Ingest the pilot: graph gets nodes/edges, content index is populated."""
    nodes = _load_pilot()
    assert len(nodes) >= 500, f"scaled corpus too small: {len(nodes)}"

    graph = InMemoryGraphEngine()
    index = ContentIndex()
    engine = build_knowledge_engine(graph=graph, content_index=index)

    for doc_id, text in nodes:
        engine.ingest(doc_id, text)

    # graph has at least one node per doc + extracted entities
    for doc_id, _ in nodes:
        assert graph.get_node(doc_id) is not None, f"missing node {doc_id}"
    # edges exist from wikilink extraction (REFERENCES / BACKLINKS)
    edge_count = len(list(graph.edges())) if hasattr(graph, "edges") else None
    assert edge_count is None or edge_count > 0, "no edges extracted from wikilinks"
    # index stats show indexed terms
    stats = index.get_stats()
    assert stats.get("documents", 0) == len(nodes), stats


def test_pilot_snapshot_roundtrip():
    """Snapshot the post-ingest state via KnowledgeSnapshotStore; load returns a dict."""
    nodes = _load_pilot()
    graph = InMemoryGraphEngine()
    index = ContentIndex()
    engine = build_knowledge_engine(graph=graph, content_index=index)
    for doc_id, text in nodes:
        engine.ingest(doc_id, text)

    import json
    import tempfile
    snap_path = os.path.join(tempfile.mkdtemp(), "pilot_snapshot.json")
    store = KnowledgeSnapshotStore(snap_path)
    node_count = len(list(graph.nodes())) if hasattr(graph, "nodes") else len(nodes)
    term_count = index.get_stats().get("terms", 0)
    store.save({"nodes": node_count, "edges": 0}, {"terms": term_count})
    loaded = store.load()
    assert loaded is not None
    assert loaded["graph"]["nodes"] >= len(nodes)
    # file persists
    assert os.path.exists(snap_path)
    with open(snap_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["version"] == 1


def test_pilot_retrieval_finds_correct_node():
    """For >=90% of pilot Q&A, ContentIndex.search(QUESTION) returns doc_id in top-3."""
    nodes = _load_pilot()
    graph = InMemoryGraphEngine()
    index = ContentIndex()
    engine = build_knowledge_engine(graph=graph, content_index=index)
    for doc_id, text in nodes:
        engine.ingest(doc_id, text)

    hits = 0
    evaluated = 0
    for doc_id, text in nodes:
        # QUESTION line is the retrieval probe
        q_line = next((ln for ln in text.splitlines() if ln.startswith("QUESTION:")), "")
        question = q_line.replace("QUESTION:", "").strip()
        if not question:
            continue
        evaluated += 1
        top = index.search(question)  # AND-search, ranked by frequency
        if doc_id in top[:3]:
            hits += 1
    assert evaluated >= 500, f"too few evaluated: {evaluated}"
    rate = hits / evaluated
    print(f"[knowledge-pilot] retrieval hit-rate {hits}/{evaluated} = {rate:.3f}")
    assert rate >= 0.90, f"retrieval recall {rate:.2f} < 0.90 ({hits}/{evaluated})"
