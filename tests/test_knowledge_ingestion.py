"""Integration test: load the 84 P0 Pilot Knowledge Nodes into the EXISTING
KROFT_OS pipeline (graph + ContentIndex + KnowledgeSnapshotStore) and prove
KROFT can actually retrieve them. No new engine/graph/storage is created.

Run:  PYTHONPATH=. python -m pytest tests/test_knowledge_ingestion.py -q
"""
from __future__ import annotations

import glob
import os
import tempfile

import pytest
import yaml

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.content_index import ContentIndex
from services.graph_query_engine import GraphQueryEngine
from composition.knowledge_persistence import KnowledgeSnapshotStore
from composition.knowledge_ingestion import ingest_directory, read_node_file

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_EVAL") != "1",
    reason="knowledge eval (ingestion) is gated; set KNOWLEDGE_EVAL=1 to run",
)

VAULT = r"C:\Users\Nikita\Documents\Obsidian Vault"
DATASET = os.path.join(VAULT, "01-Knowledge", "KROFT_KNOWLEDGE")


def _load_nodes():
    nodes = []
    for f in glob.glob(os.path.join(DATASET, "**", "KROFT-*.md"), recursive=True):
        nodes.append(read_node_file(f))
    return nodes


def test_dataset_present():
    nodes = _load_nodes()
    assert len(nodes) == 84, f"expected 84 P0 nodes, found {len(nodes)}"


def test_ingest_84_reads_all():
    r = ingest_directory(DATASET)
    c = r["counts"]
    assert c["files"] == 84
    assert c["read_errors"] == 0
    assert c["added_nodes"] == 84


def test_ingest_84_valid():
    # every node has the required semantic fields (frontmatter preserved)
    nodes = _load_nodes()
    req = ["id", "layer", "domain", "topic", "priority", "knowledge_type",
           "qna_type", "question", "answer", "source", "confidence", "validity",
           "related_concepts", "prerequisites", "tags"]
    bad = [n.get("id", "?") for n in nodes if any(k not in n for k in req)]
    assert not bad, f"nodes missing fields: {bad}"


def test_semantic_state_contains_nodes():
    tmp = tempfile.mkdtemp()
    snap = os.path.join(tmp, "snap.json")
    store = KnowledgeSnapshotStore(snap)
    r = ingest_directory(DATASET, store=store, snapshot_path=snap)
    data = store.load()
    assert data is not None
    sem = data.get("semantic", [])
    assert len(sem) == 84, f"semantic state has {len(sem)} nodes"
    ids = {n["id"] for n in sem}
    assert len(ids) == 84


def test_graph_edges_created():
    r = ingest_directory(DATASET)
    eng = r["engine"]
    g = r["builder"].get_graph()
    assert len(g["edges"]) > 0, "no graph edges created"
    assert len(eng.nodes_by_tag("source:SRC-002")) > 0


def test_provenance_preserved():
    r = ingest_directory(DATASET)
    c = r["counts"]
    assert c["provenance_missing"] == 0
    g = r["builder"].get_graph()
    miss = [n["id"] for n in g["nodes"] if not n.get("meta", {}).get("source", {}).get("id")]
    assert not miss, f"provenance missing in graph: {miss}"


def test_snapshot_save_reload_identical():
    tmp = tempfile.mkdtemp()
    snap = os.path.join(tmp, "snap.json")
    store = KnowledgeSnapshotStore(snap)
    r = ingest_directory(DATASET, store=store, snapshot_path=snap)
    reloaded = store.load()
    assert reloaded is not None
    sem = reloaded["semantic"]
    assert len(sem) == 84
    orig = {n["id"]: n for n in _load_nodes()}
    for n in sem:
        nid = n["id"]
        assert n.get("question") == orig[nid].get("question"), f"question drift {nid}"
        assert n.get("answer") == orig[nid].get("answer"), f"answer drift {nid}"
        assert n.get("source", {}).get("id") == orig[nid].get("source", {}).get("id")


def test_graph_verification_methods():
    r = ingest_directory(DATASET)
    eng = r["engine"]
    target = "KROFT-Q-000006"
    nb = [x["id"] for x in eng.get_neighbors(target)]
    assert target in eng.backlinks(nb[0]) if nb else True
    assert len(eng.nodes_by_tag("Systems")) > 0


def _golden_queries():
    """Build 20 queries from words actually present in the target node text so
    the AND full-text index is guaranteed to hit (tests PIPELINE, not DATA)."""
    nodes = _load_nodes()
    # take 20 representative nodes across the 5 P0 areas (L02-L06)
    picks = [n["id"] for n in nodes if n["layer"] in ("L02", "L03", "L04", "L05", "L06")][:20]
    by_id = {n["id"]: n for n in nodes}
    queries = []
    for pid in picks:
        n = by_id[pid]
        text = (n.get("question", "") + " " + n.get("answer", "")).lower()
        toks = [w for w in text.split() if len(w) > 4][:4]
        q = " ".join(toks)
        queries.append((pid, q, n.get("question", "")))
    return queries


@pytest.mark.parametrize("pid,query,orig_q", _golden_queries())
def test_20_golden_retrieval(pid, query, orig_q):
    r = ingest_directory(DATASET)
    eng = r["engine"]
    res = eng.search(query)
    assert pid in res, f"golden query [{query}] missed target {pid}; got {res[:5]}"


def test_retrieval_categories():
    r = ingest_directory(DATASET)
    eng = r["engine"]
    assert "KROFT-Q-000006" in eng.search("false sharing")
    assert "KROFT-Q-000019" in eng.nodes_by_tag("SE")
    nb = [x["id"] for x in eng.get_neighbors("KROFT-Q-000006")]
    assert len(nb) > 0
    assert len(eng.nodes_by_tag("source:SRC-002")) > 0
    assert "KROFT-Q-000008" in eng.nodes_by_tag("source:SRC-002")
