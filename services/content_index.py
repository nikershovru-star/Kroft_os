"""ContentIndex — in-memory inverted index for full-text search (Stage 18).

Closes the Stage-10 honest limitation "No content indexing — the crawler
stores node labels + extracted tags in metadata but does NOT index full
file text for search".

Structure:
  _index:     word -> set[node_id]          (posting lists, AND-intersection)
  _doc_terms: node_id -> Counter(word)      (reverse map: O(doc-terms) removal
                                             + match-frequency sort in search)

Tokenization: regex \\w+, lowercased, tokens shorter than 2 chars dropped.
No stemming, no stop-words, no phrase search, no fuzzy match — see the
HONEST LIMITATIONS (Stage 18) section in README.

Architecture contract: stdlib only (re, collections) — a strict subset of
the allowed axis (contracts + stdlib). Never imports adapters, kernel, cli,
infrastructure or sibling services (enforced by tests/test_architecture.py).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Set

_TOKEN_RE = re.compile(r"\w+")
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> List[str]:
    """\\w+ tokens, lowercased, len >= 2. No stemming / stop-words."""
    return [
        t for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) >= _MIN_TOKEN_LEN
    ]


class ContentIndex:
    """In-memory inverted index: word -> posting list of node_ids."""

    def __init__(self) -> None:
        self._index: Dict[str, Set[str]] = {}
        self._doc_terms: Dict[str, Counter] = {}

    def index_file(self, node_id: str, text: str) -> None:
        """(Re)index a document. REPLACE semantics: previous terms for this
        node_id are dropped first, so re-indexing (full re-crawl or an
        incremental changed-file rescan) never leaves stale terms and never
        double-counts frequencies.
        """
        self.remove_file(node_id)
        counts = Counter(_tokenize(text))
        if not counts:
            return
        self._doc_terms[node_id] = counts
        for word in counts:
            self._index.setdefault(word, set()).add(node_id)

    def search(self, query: str) -> List[str]:
        """AND-search: node_ids containing ALL query tokens.

        Result is sorted by total match frequency (sum of query-term
        occurrences in the document, descending), then node_id ascending
        for determinism. Empty/short-token-only query -> [].
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        result: Set[str] | None = None
        for tok in tokens:
            postings = self._index.get(tok)
            if not postings:
                return []  # AND-logic: one missing term kills the match
            result = set(postings) if result is None else (result & postings)
            if not result:
                return []
        assert result is not None
        return sorted(
            result,
            key=lambda nid: (
                -sum(self._doc_terms[nid][t] for t in tokens),
                nid,
            ),
        )

    def remove_file(self, node_id: str) -> None:
        """Drop node_id from every posting list it appears in.

        Uses the reverse map — O(terms of this doc), not O(all terms).
        Empty posting lists are pruned so get_stats() stays honest.
        """
        counts = self._doc_terms.pop(node_id, None)
        if not counts:
            return
        for word in counts:
            postings = self._index.get(word)
            if postings is None:
                continue
            postings.discard(node_id)
            if not postings:
                del self._index[word]

    def get_stats(self) -> Dict[str, int]:
        return {"terms": len(self._index), "documents": len(self._doc_terms)}
