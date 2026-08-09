"""Rewriting embedding adapter (ADR-0XX, P0-B).

K6-compliant: adapters/ imports ONLY contracts.* + stdlib. Wraps any IEmbedding:
before embedding a *query*, it is expanded by a QueryExpander so paraphrase queries
land closer to the canonical node vocabulary already embedded in the index.

The underlying IEmbedding (e.g. OllamaEmbeddingAdapter/bge-m3) is unchanged — this
adapter only rewrites the query text, never the document side (documents stay as-is
to avoid index rebuilds). Integration point: composition/knowledge_ingestion.py wires
RewritingEmbedding(base=ollama) into GraphQueryEngine.

Graceful (O1): if the expander is None, query passes through verbatim (zero regression).
"""
from __future__ import annotations

from typing import List, Optional

from contracts import IEmbedding
from adapters.query_expander import QueryExpander


class RewritingEmbedding(IEmbedding):
    """IEmbedding that rewrites queries (not documents) before embedding."""

    def __init__(self, base: IEmbedding, expander: Optional[QueryExpander] = None) -> None:
        if base is None:
            raise TypeError("RewritingEmbedding requires a base IEmbedding instance")
        self._base = base
        self._expander = expander or QueryExpander()

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            return self._base.embed(text)
        rewritten = self._expander.expand(text)
        # If expansion produced nothing useful, fall back to the raw text.
        target = rewritten if rewritten else text
        return self._base.embed(target)
