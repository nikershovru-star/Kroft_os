"""L10.9 — read-only foundation_eval must NOT mutate production.

Proves the KROFT_EVAL_READONLY=1 path:
- does NOT call foundation_ingest.build() (no ingest / rebuild / re-embed)
- does NOT call KnowledgeSnapshotStore.save() (no production write)
- CAN load an existing snapshot + run retrieval over it

The production _snapshot.json is never touched. The test injects a tiny
in-memory snapshot via monkeypatched KnowledgeSnapshotStore.load and a fake
Ollama embedder, so it runs deterministically without Ollama and without
any filesystem side effect.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# A minimal snapshot: 2 chunks from 1 source, with vectors + lexical index.
_FAKE_SNAPSHOT = {
    "version": 1,
    "graph": {"nodes": [], "edges": []},
    "index": {
        "_index": {
            "shannon": {"KROFT-FND-claude_shannon_a-001"},
            "entropy": {"KROFT-FND-claude_shannon_a-001"},
            "wiener": {"KROFT-FND-norbert_wiener-001"},
        },
        "_doc_terms": {
            "KROFT-FND-claude_shannon_a-001": {"shannon": 1, "entropy": 1},
            "KROFT-FND-norbert_wiener-001": {"wiener": 1},
        },
    },
    "semantic": [
        {"id": "KROFT-FND-claude_shannon_a-001",
         "source": {"id": "claude_shannon_a.pdf"}},
        {"id": "KROFT-FND-norbert_wiener-001",
         "source": {"id": "norbert_wiener.pdf"}},
    ],
    "semantic_vectors": {
        "KROFT-FND-claude_shannon_a-001": [0.9, 0.1, 0.0],
        "KROFT-FND-norbert_wiener-001": [0.0, 0.1, 0.9],
    },
}


def _fake_embed(text):
    # Deterministic pseudo-embedding: keyword-driven, no network.
    if "shannon" in text.lower():
        return [0.9, 0.1, 0.0]
    if "wiener" in text.lower():
        return [0.0, 0.1, 0.9]
    return [0.1, 0.1, 0.1]


def test_readonly_eval_does_not_call_build_or_save(capsys):
    """Read-only mode loads snapshot + measures, without build()/save()."""
    import scripts.foundation_eval as fe

    build_spy = MagicMock(side_effect=AssertionError("build() must NOT run in read-only mode"))
    save_spy = MagicMock(side_effect=AssertionError("store.save() must NOT run in eval"))

    with patch.object(fe, "build", build_spy), \
         patch.object(fe.KnowledgeSnapshotStore, "load",
               return_value=dict(_FAKE_SNAPSHOT)), \
         patch.object(fe.KnowledgeSnapshotStore, "save",
               save_spy), \
         patch("adapters.ollama_embedding.OllamaEmbeddingAdapter.embed",
               side_effect=_fake_embed), \
         patch.dict(os.environ, {"KROFT_EVAL_READONLY": "1"}):
        rc = fe.main()

    assert rc == 0, "read-only eval should exit 0"
    build_spy.assert_not_called()
    save_spy.assert_not_called()
    out = capsys.readouterr().out
    assert "read-only LOAD" in out, "should report read-only LOAD mode"
    assert "RETRIEVAL EVAL DONE" in out, "should complete evaluation"


def test_readonly_eval_runs_retrieval_on_loaded_snapshot(capsys):
    """hybrid_search over restored indexes returns hits for a known query."""
    import scripts.foundation_eval as fe

    with patch("composition.knowledge_persistence.KnowledgeSnapshotStore.load",
               return_value=dict(_FAKE_SNAPSHOT)), \
         patch("adapters.ollama_embedding.OllamaEmbeddingAdapter.embed",
               side_effect=_fake_embed), \
         patch.dict(os.environ, {"KROFT_EVAL_READONLY": "1"}):
        rc = fe.main()

    assert rc == 0
    out = capsys.readouterr().out
    # factual/cross/negative blocks should have printed metric lines
    assert "R@5=" in out, "expected per-category Recall lines"
