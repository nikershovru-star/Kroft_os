"""Retrieval-augmented reasoning proof (ТЗ: kernel references the live corpus during tick).

Deterministic + fast (no gate). Builds a tmp corpus of 3 nodes, boots KroftApp with
knowledge_corpus pointing at it, runs one tick whose goal text MATCHES one node's
QUESTION, and asserts the kernel's selected plan steps contain the injected
`knowledge: <node_id>:` context. The inverse case (no corpus wired) asserts NO
injection — so abstract deliberation (choose_blue/red) stays clean + deterministic.

Reuses the existing live-wiring (knowledge_corpus -> _ingest_corpus -> ContentIndex)
and the existing tick/injection path (mirror of past-experience injection). The kernel
receives the wired ContentIndex via KernelConfig.knowledge_index; retrieval core and
the 10k+ corpus are untouched.

Run:
    PYTHONPATH=. python -m pytest tests/knowledge/test_knowledge_reasoning.py -v
"""

import os

import pytest

from composition.run_kroft import KroftApp, KroftConfig


def _write_tmp_corpus(tmp_path):
    docs = {
        "qa_tmp_alpha": "What is the retrieval-augmented reasoning test marker alpha?",
        "qa_tmp_beta": "What is the retrieval-augmented reasoning test marker beta?",
        "qa_tmp_gamma": "What is the retrieval-augmented reasoning test marker gamma?",
    }
    for nid, q in docs.items():
        (tmp_path / f"{nid}.md").write_text(
            "# %s\n\nTYPE: FACTUAL\nCONFIDENCE: high\nPROVENANCE: test:tmp\nTTL: 0\n\n"
            "QUESTION: %s\nANSWER: marker answer for %s.\nRELATIONS: [[Test]]\n"
            % (nid, q, nid),
            encoding="utf-8",
        )
    return docs


def test_knowledge_injection_present_with_corpus(tmp_path):
    _write_tmp_corpus(tmp_path)
    app = KroftApp(KroftConfig(
        node_id="t", llm="none", ticks=0, knowledge_corpus=str(tmp_path)))
    app.step("What is the retrieval-augmented reasoning test marker alpha?")
    plan = app.kernel._last_selected_plan
    assert plan is not None, "no plan selected"
    joined = " ".join(str(s) for s in plan.steps)
    assert "knowledge: qa_tmp_alpha:" in joined, joined


def test_knowledge_injection_absent_without_corpus(tmp_path):
    _write_tmp_corpus(tmp_path)  # corpus exists but is NOT wired
    app = KroftApp(KroftConfig(node_id="t", llm="none", ticks=0))  # no knowledge_corpus
    app.step("What is the retrieval-augmented reasoning test marker alpha?")
    plan = app.kernel._last_selected_plan
    assert plan is not None, "no plan selected"
    joined = " ".join(str(s) for s in plan.steps)
    assert "knowledge:" not in joined, joined
