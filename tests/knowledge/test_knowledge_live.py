"""Gated live retrieval-augmented proof for the KROFT_KNOWLEDGE corpus.

KroftApp is wired (ТЗ-KNOWLEDGE-LIVE) so that, when KroftConfig.knowledge_corpus
points at the corpus dir, it is ingested lazily on the first query (boot stays
fast even for a 10k+ corpus) and app.query(question) returns a top-3 node list
with a leading citation (node_id).

This is a HEAVY gate: it boots the full KroftApp and ingests the live corpus on
the first query. It is gated behind KNOWLEDGE_LIVE=1 and SKIPPED by default so
the always-run suite never boots/ingests the corpus.

Run manually:
    KNOWLEDGE_LIVE=1 PYTHONPATH=. python -m pytest tests/knowledge/test_knowledge_live.py -v

K5/K6: reuses KnowledgeEngine + ContentIndex inside KroftApp. No contracts change;
retrieval core, pilot test, and scale test are untouched.
"""

import os
import random

import pytest

from composition.run_kroft import KroftApp, KroftConfig

PILOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "KROFT_KNOWLEDGE",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_LIVE") != "1",
    reason="live retrieval-augmented proof is gated; set KNOWLEDGE_LIVE=1 to run",
)


def _corpus_qa():
    files = sorted(
        f for f in os.listdir(PILOT_DIR)
        if f.startswith("qa_") and f.endswith(".md")
    )
    out = []
    for f in files:
        doc_id = f[:-3]
        with open(os.path.join(PILOT_DIR, f), encoding="utf-8") as fh:
            text = fh.read()
        q = next(
            (ln.replace("QUESTION:", "").strip()
             for ln in text.splitlines() if ln.startswith("QUESTION:")),
            "",
        )
        if q:
            out.append((doc_id, q))
    return out


def test_live_retrieval_augmented():
    """For >=90% of 200 sampled questions, app.query() returns the source node
    in top-3 and carries a citation (node_id)."""
    cfg = KroftConfig(knowledge_corpus=PILOT_DIR)
    app = KroftApp(cfg)

    qa = _corpus_qa()
    assert len(qa) >= 200, f"corpus too small to sample 200: {len(qa)}"
    random.seed(42)
    sample = random.sample(qa, 200)

    hits = 0
    cited = 0
    for doc_id, question in sample:
        res = app.query(question)
        if doc_id in res["top3"]:
            hits += 1
        if res["citation"]:
            cited += 1

    rate = hits / len(sample)
    print(f"[knowledge-live] retrieval hit-rate {hits}/{len(sample)} = {rate:.4f}; "
          f"cited {cited}/{len(sample)}")
    assert rate >= 0.90, f"live retrieval recall {rate:.2f} < 0.90 ({hits}/{len(sample)})"
    assert cited == len(sample), f"every query must return a citation, got {cited}/{len(sample)}"
