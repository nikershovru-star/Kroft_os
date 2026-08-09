"""P0-B proof-of-fire: RU/EN query rewrite lifts paraphrase-overlap (ADR-0XX).

Self-contained — NO Ollama. Uses a deterministic fake embedding (token-overlap
cosine) to PROVE that rewriting a paraphrased query moves it closer to the
canonical node vocabulary than the raw query does.

Proves:
  - raw paraphrase query has LOW overlap with canonical node;
  - rewritten query has >= overlap (rewrite recovers canonical synonyms);
  - RewritingEmbedding delegates the EXPANDED text to the base embedder;
  - stopwords are dropped, empty/unknown query does not crash.
"""
from __future__ import annotations

from typing import List

import pytest

from adapters.query_expander import QueryExpander
from adapters.rewriting_embedding import RewritingEmbedding
from contracts import IEmbedding


def _fake_embed(text: str) -> List[float]:
    """Deterministic token-overlap embedding in a fixed vocab space (test only)."""
    vocab = ["конфигурация", "инструкция", "запуск", "агент", "граф", "память", "модель"]
    vec = [0.0] * len(vocab)
    for i, w in enumerate(vocab):
        if w in (text or "").lower():
            vec[i] = 1.0
    return vec


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _node_vec():
    # canonical node text uses canonical vocabulary
    return _fake_embed("конфигурация инструкция запуск агент")


def test_rewrite_recovers_canonical_overlap_on_paraphrase():
    node = _node_vec()
    raw = "как настроить и запустить бота"          # paraphrase: настроить/бот not canonical
    rew = QueryExpander().expand(raw)
    assert "конфигурация" in rew   # настроить -> конфигурация
    assert "агент" in rew           # бот -> агент
    raw_cos = _cosine(_fake_embed(raw), node)
    rew_cos = _cosine(_fake_embed(rew), node)
    assert rew_cos > raw_cos, (raw_cos, rew_cos)


def test_rewriting_embedding_delegates_expanded_text():
    calls = []
    class _Spy(IEmbedding):
        def embed(self, text):
            calls.append(text)
            return _fake_embed(text)
    spy = _Spy()
    rw = RewritingEmbedding(base=spy, expander=QueryExpander())
    rw.embed("как настроить агента")
    assert len(calls) == 1
    # the base embedder received the EXPANDED text, not the raw one
    assert "конфигурация" in calls[0] and "агент" in calls[0]
    assert "настроить" not in calls[0]   # paraphrase replaced by canonical


def test_stopwords_and_empty_safe():
    ex = QueryExpander()
    assert ex.expand("") == ""
    assert "как" not in ex.expand("как запустить агента").split()
    # unknown tokens pass through unchanged
    assert "xyzterm" in ex.expand("xyzterm запуск").split()


def test_rewriting_embedding_none_base_raises():
    with pytest.raises(TypeError):
        RewritingEmbedding(base=None)
