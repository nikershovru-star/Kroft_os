"""SemanticMemoryStub — keyword-based ISemanticMemory (Wave 9, ADR-012 Phase E).

v0.1 deliberately ships WITHOUT embeddings: no numpy, no torch, no
sentence-transformers (ADR-012 §3, stdlib-first). Ranking is token-overlap
(Jaccard-ish), which is honest about being a placeholder — the value here is
that the CONTRACT is ready, so v1.0 swaps in an Ollama `/api/embed` adapter
without touching `services/`.

Knowledge integration (ADR-012 §2.4): facts from the Wave 8 graph are a
retrieval source. The spec called for `KnowledgePlatform.query()`, which does
not exist (the platform exposes `facts()` / `find()`), and importing a service
from an adapter would break LAW 2 anyway. So the source is injected as a plain
callable returning fact-like objects — read-only, engine-agnostic.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, List, Optional

from contracts.i_memory import (
    IMemoryStore,
    ISemanticMemory,
    MemoryItem,
    MemoryKind,
    MemoryQuery,
)

FactSource = Callable[[], Iterable[Any]]

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# tokens too generic to carry meaning in a 2-3 word query
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
        "and", "or", "it", "this", "that", "what", "who", "how",
        "и", "в", "на", "с", "по", "это", "что", "как", "кто", "мой", "моя",
    }
)


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS}


class SemanticMemoryStub(ISemanticMemory):
    """Keyword-overlap retrieval over a memory store plus (optionally) facts.

    Args:
        store: the IMemoryStore to search (usually Long-Term).
        fact_source: optional zero-arg callable returning Fact-like objects
            (`subject`/`predicate`/`object`), e.g. `knowledge_platform.facts`.
            Read-only; the graph is never written from here.
    """

    def __init__(
        self,
        store: IMemoryStore,
        fact_source: Optional[FactSource] = None,
    ) -> None:
        self._store = store
        self._fact_source = fact_source

    # --- ISemanticMemory ---------------------------------------------------
    def search(self, text: str, limit: int = 5) -> List[MemoryItem]:
        wanted = _tokens(text)
        if not wanted:
            return []

        scored = []
        for item in self._store.query(MemoryQuery()):
            score = self._score(wanted, item.content)
            if score > 0:
                scored.append((score, item.importance, item.timestamp, item))

        for item in self._facts_as_items():
            score = self._score(wanted, item.content)
            if score > 0:
                scored.append((score, item.importance, item.timestamp, item))

        # relevance, then importance, then recency
        scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
        return [t[3] for t in scored[: max(0, limit)]]

    # --- internals ---------------------------------------------------------
    @staticmethod
    def _score(wanted: set, content: str) -> float:
        have = _tokens(content)
        if not have:
            return 0.0
        overlap = wanted & have
        if not overlap:
            return 0.0
        return len(overlap) / float(len(wanted))

    def _facts_as_items(self) -> List[MemoryItem]:
        """Project Wave 8 Facts into MemoryItems (read-only view)."""
        if self._fact_source is None:
            return []
        try:
            facts = list(self._fact_source())
        except Exception:  # noqa: BLE001 — a broken source must not kill retrieval
            return []

        out: List[MemoryItem] = []
        for f in facts:
            subject = getattr(f, "subject", None)
            predicate = getattr(f, "predicate", None)
            obj = getattr(f, "object", None)
            if not (subject and predicate and obj):
                continue
            out.append(
                MemoryItem(
                    key=f"fact:{subject}:{predicate}:{obj}",
                    content=f"{subject} {predicate} {obj}",
                    importance=float(getattr(f, "confidence", 1.0) or 0.0),
                    tags=(MemoryKind.LONG_TERM, MemoryKind.SEMANTIC, "fact"),
                    source=str(getattr(f, "source", "knowledge_graph")),
                )
            )
        return out
