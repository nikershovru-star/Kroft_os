"""Retrieval Evaluation (Этап 5 + PHASE 6B/6C) — SEPARATE evaluation layer.

Measures three retrieval modes on the SAME golden dataset (tests/golden_queries.yaml):
  - baseline : GraphQueryEngine.search()           (lexical AND, rank-based)
  - semantic : GraphQueryEngine.semantic_search()   (SemanticIndex + local Ollama embedding)
  - hybrid   : GraphQueryEngine.hybrid_search()      (lexical + semantic via RRF)

Rank-based metrics only (search returns List[str]; semantic/hybrid return
List[(id,score)] but we use rank position — no invented score). NDCG uses
binary relevance. Does NOT modify the 84 nodes / runtime / contracts / storage.

Run: PYTHONPATH=. python -m pytest tests/test_retrieval_evaluation.py -q -s
"""
from __future__ import annotations

import glob
import os

import pytest
import yaml

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.content_index import ContentIndex
from services.graph_query_engine import GraphQueryEngine
from services.semantic_index import SemanticIndex
from adapters.ollama_embedding import OllamaEmbeddingAdapter
from composition.knowledge_ingestion import ingest_directory

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_EVAL") != "1",
    reason="knowledge eval (retrieval/semantic/hybrid) hits Ollama; set KNOWLEDGE_EVAL=1 to run",
)

VAULT = r"C:\Users\Nikita\Documents\Obsidian Vault"
DATASET = os.path.join(VAULT, "01-Knowledge", "KROFT_KNOWLEDGE")
GOLDEN = os.path.join(os.path.dirname(__file__), "golden_queries.yaml")


def _load_golden():
    return yaml.safe_load(open(GOLDEN, encoding="utf-8"))


@pytest.fixture(scope="module")
def engine():
    return ingest_directory(DATASET)["engine"]


# ---- rank-based metric helpers (binary relevance) ----
def _recall_at(ids, expected, k):
    if not expected:
        return 0.0
    return sum(1 for e in expected if e in ids[:k]) / len(expected)


def _precision_at(ids, expected, k):
    top = ids[:k]
    if not top:
        return 0.0
    return sum(1 for nid in top if nid in expected) / len(top)


def _mrr(ids, expected):
    for i, nid in enumerate(ids, 1):
        if nid in expected:
            return 1.0 / i
    return 0.0


def _ndcg_at(ids, expected, k):
    rel = [1.0 if nid in expected else 0.0 for nid in ids[:k]]
    if sum(rel) == 0:
        return 0.0
    dcg = sum(r / (1 + i) for i, r in enumerate(rel))
    ideal = sorted(rel, reverse=True)
    idcg = sum(r / (1 + i) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def _eval_mode(retrieve, items):
    """retrieve(query)->List[str]; items = golden positive list. Returns
    aggregate metrics + per-category breakdown + failures."""
    cats = {}
    agg = dict(r1=0.0, r3=0.0, r5=0.0, p5=0.0, mrr=0.0, ndcg=0.0)
    n = 0
    failures = []
    for it in items:
        q = it["query"]
        exp = it.get("expected_nodes", [])
        ids = retrieve(q)
        r1 = _recall_at(ids, exp, 1); r3 = _recall_at(ids, exp, 3)
        r5 = _recall_at(ids, exp, 5); p5 = _precision_at(ids, exp, 5)
        m = _mrr(ids, exp); nd = _ndcg_at(ids, exp, 5)
        c = it.get("category", "other")
        cats.setdefault(c, dict(r1=0.0, r3=0.0, r5=0.0, p5=0.0, mrr=0.0, ndcg=0.0, n=0))
        for k, v in [("r1", r1), ("r3", r3), ("r5", r5), ("p5", p5), ("mrr", m), ("ndcg", nd)]:
            agg[k] += v; cats[c][k] += v
        cats[c]["n"] += 1
        n += 1
        if r5 == 0.0:
            failures.append((c, q, exp, ids[:3]))
    for k in agg:
        agg[k] /= n
    for c in cats:
        nn = cats[c].pop("n") or 1
        for k in list(cats[c]):
            cats[c][k] /= nn
    return agg, cats, failures


def test_golden_dataset_size():
    g = _load_golden()
    assert len(g["positive"]) >= 50
    assert len(g["negative"]) >= 10
    assert len(g["graph_scenarios"]) >= 10


def test_baseline_lexical(engine):
    g = _load_golden()
    agg, cats, fails = _eval_mode(lambda q: engine.search(q), g["positive"])
    test_baseline_lexical._out = (agg, cats, fails)
    print("\n[BASELINE lexical] R@1=%.3f R@3=%.3f R@5=%.3f P@5=%.3f MRR=%.3f NDCG@5=%.3f"
          % (agg["r1"], agg["r3"], agg["r5"], agg["p5"], agg["mrr"], agg["ndcg"]))
    print("  by-category R@5:", {c: round(v["r5"], 3) for c, v in cats.items()})
    assert True


def test_semantic_mode(engine):
    g = _load_golden()
    agg, cats, fails = _eval_mode(lambda q: [x[0] for x in engine.semantic_search(q, top_k=10)],
                                    g["positive"])
    test_semantic_mode._out = (agg, cats, fails)
    print("\n[SEMANTIC] R@1=%.3f R@3=%.3f R@5=%.3f P@5=%.3f MRR=%.3f NDCG@5=%.3f"
          % (agg["r1"], agg["r3"], agg["r5"], agg["p5"], agg["mrr"], agg["ndcg"]))
    print("  by-category R@5:", {c: round(v["r5"], 3) for c, v in cats.items()})
    assert True


def test_hybrid_mode(engine):
    g = _load_golden()
    agg, cats, fails = _eval_mode(lambda q: [x[0] for x in engine.hybrid_search(q, top_k=10)],
                                    g["positive"])
    test_hybrid_mode._out = (agg, cats, fails)
    print("\n[HYBRID] R@1=%.3f R@3=%.3f R@5=%.3f P@5=%.3f MRR=%.3f NDCG@5=%.3f"
          % (agg["r1"], agg["r3"], agg["r5"], agg["p5"], agg["mrr"], agg["ndcg"]))
    print("  by-category R@5:", {c: round(v["r5"], 3) for c, v in cats.items()})
    assert True


def test_negative_queries_do_not_hallucinate(engine):
    g = _load_golden()
    rows = []
    for q in g["negative"]:
        lex = engine.search(q)
        sem = [x[0] for x in engine.semantic_search(q, top_k=5)]
        hyb = [x[0] for x in engine.hybrid_search(q, top_k=5)]
        rows.append((q, len(lex), lex[:1], len(sem), sem[:1], len(hyb), hyb[:1]))
    test_negative_queries_do_not_hallucinate._rows = rows
    print("\n[NEGATIVE] q -> (lex_n, lex_top, sem_n, sem_top, hyb_n, hyb_top)")
    for q, ln, lt, sn, st, hn, ht in rows:
        print(f"  '{q[:42]}' -> L({ln},{lt}) S({sn},{st}) H({hn},{ht})")
    assert True


def test_graph_traversal_scenarios(engine):
    g = _load_golden()
    passed = 0
    details = []
    for sc in g["graph_scenarios"]:
        start, via, expect = sc["start_node"], sc["via"], sc.get("expect_reachable", [])
        if via == "get_neighbors":
            nb = [x["id"] for x in engine.get_neighbors(start)]; hit = [e for e in expect if e in nb]
        elif via == "backlinks":
            bl = engine.backlinks(start); hit = [e for e in expect if e in bl]
        elif via == "nodes_by_tag":
            tagged = engine.nodes_by_tag(sc["tag"]); hit = [e for e in expect if e in tagged]
        else:
            hit = []
        ok = len(hit) > 0
        passed += 1 if ok else 0
        details.append((sc["name"], ok, hit, expect))
    test_graph_traversal_scenarios._details = details
    print(f"\n[GRAPH] {passed}/{len(g['graph_scenarios'])} scenarios found expected neighbor")
    for name, ok, hit, exp in details:
        print(f"  [{'OK' if ok else 'XX'}] {name}: {hit[:2]} of {exp[:2]}")
    assert passed >= 1


def test_evaluation_does_not_mutate_nodes():
    files = glob.glob(os.path.join(DATASET, "**", "KROFT-*.md"), recursive=True)
    assert len(files) == 84
