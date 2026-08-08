"""Gated KROFT_KNOWLEDGE scale proof (>=10k Q&A, retrieval >=90%).

This is a HEAVY test: it ingests the full scaled corpus (>=10,000 qa_*.md) and
checks that ContentIndex.search (with the exact-phrase rerank) still finds the
correct node for >=90% of the corpus. It is gated behind KNOWLEDGE_SCALE=1 and
SKIPPED by default so the always-run suite never ingests 10k docs.

Run manually:
    KNOWLEDGE_SCALE=1 PYTHONPATH=. python -m pytest tests/knowledge/test_knowledge_scale.py -v

K5/K6: reuses KnowledgeEngine + InMemoryGraphEngine + ContentIndex. No contracts
change; retrieval core untouched.
"""

import os
import pytest

from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine

PILOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "KROFT_KNOWLEDGE",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_SCALE") != "1",
    reason="scale retrieval proof is gated; set KNOWLEDGE_SCALE=1 to run",
)


def _load_corpus():
    files = sorted(
        f for f in os.listdir(PILOT_DIR)
        if f.startswith("qa_") and f.endswith(".md")
    )
    nodes = []
    for f in files:
        doc_id = f[:-3]
        with open(os.path.join(PILOT_DIR, f), encoding="utf-8") as fh:
            text = fh.read()
        nodes.append((doc_id, text))
    return nodes


def test_scale_corpus_is_large():
    """Guard: the scaled corpus must actually be >=10,000 nodes."""
    nodes = _load_corpus()
    assert len(nodes) >= 10_000, f"scaled corpus too small: {len(nodes)}"


def test_scale_retrieval_hit_rate():
    """For >=90% of the scaled corpus, ContentIndex.search(QUESTION) returns
    the node in the top-3 (exact-phrase rerank keeps recall at ~100%)."""
    nodes = _load_corpus()
    assert len(nodes) >= 10_000, f"scaled corpus too small: {len(nodes)}"

    graph = InMemoryGraphEngine()
    index = ContentIndex()
    engine = build_knowledge_engine(graph=graph, content_index=index)
    for doc_id, text in nodes:
        engine.ingest(doc_id, text)

    hits = 0
    evaluated = 0
    for doc_id, text in nodes:
        q_line = next(
            (ln for ln in text.splitlines() if ln.startswith("QUESTION:")),
            "",
        )
        question = q_line.replace("QUESTION:", "").strip()
        if not question:
            continue
        evaluated += 1
        top = index.search(question)
        if doc_id in top[:3]:
            hits += 1

    assert evaluated >= 10_000
    rate = hits / evaluated
    print(f"[knowledge-scale] retrieval hit-rate {hits}/{evaluated} = {rate:.4f}")
    assert rate >= 0.90, f"scale retrieval recall {rate:.2f} < 0.90 ({hits}/{evaluated})"
