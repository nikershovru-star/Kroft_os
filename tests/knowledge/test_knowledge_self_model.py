"""Gated KROFT Self-Model retrieval proof (KNOWLEDGE_LIVE).

Self-Model nodes (type=SELF, provenance=self:KROFT, ttl=0) are generated from
the REAL repo: one qa_self_adr_0XX.md per ADR-*.md (docs/architecture) plus
qa_self_mod_* per key module, and two explicit proof nodes
(qa_self_knowledge_layer, qa_self_persistence). They live in KROFT_KNOWLEDGE/self/
so the 10k+ scaled corpus and the always-run suite are untouched.

This test boots KroftApp with knowledge_corpus pointed at that dir and verifies
the live wiring (exact-phrase rerank) returns the correct SELF node in top-3 for
the two canonical self-reflection questions, each carrying a citation (node_id).

HEAVY + gated behind KNOWLEDGE_LIVE=1; SKIPPED by default so the always-run suite
never boots/ingests. K5/K6: reuses KnowledgeEngine + ContentIndex via KroftApp;
retrieval core and the scaled corpus are untouched.

Run manually:
    KNOWLEDGE_LIVE=1 PYTHONPATH=. python -m pytest tests/knowledge/test_knowledge_self_model.py -v
"""

import os

import pytest

from composition.run_kroft import KroftApp, KroftConfig

SELF_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "KROFT_KNOWLEDGE", "self",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("KNOWLEDGE_LIVE") != "1",
    reason="self-model retrieval proof is gated; set KNOWLEDGE_LIVE=1 to run",
)


def _self_nodes():
    out = []
    for f in sorted(os.listdir(SELF_DIR)):
        if not (f.startswith("qa_self_") and f.endswith(".md")):
            continue
        doc_id = f[:-3]
        with open(os.path.join(SELF_DIR, f), encoding="utf-8") as fh:
            text = fh.read()
        q = next(
            (ln.replace("QUESTION:", "").strip()
             for ln in text.splitlines() if ln.startswith("QUESTION:")),
            "",
        )
        out.append((doc_id, q))
    return out


def test_self_model_nodes_exist():
    nodes = _self_nodes()
    assert len(nodes) >= 40, f"expected >=40 self nodes, got {len(nodes)}"


def test_self_model_retrieval_proof():
    """The two canonical self-reflection questions must return their SELF node
    in top-3 with a citation (node_id)."""
    cfg = KroftConfig(knowledge_corpus=SELF_DIR)
    app = KroftApp(cfg)

    cases = [
        "Где находится Knowledge Layer в KROFT_OS?",
        "Как работает persistence в KROFT_OS?",
    ]
    for question in cases:
        res = app.query(question)
        assert res["top3"], f"no retrieval for: {question}"
        assert res["citation"] is not None, f"no citation for: {question}"
        # the source SELF node must be present in top-3
        src = next(
            (doc_id for doc_id, q in _self_nodes() if q == question), None)
        assert src is not None, f"source node missing for: {question}"
        assert src in res["top3"], (
            f"self-model node {src} not in top-3 for '{question}': {res['top3']}")
