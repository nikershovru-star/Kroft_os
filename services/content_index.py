r"""ContentIndex — in-memory inverted index for full-text search (Stage 18 + 20).

Closes the Stage-10 honest limitation "No content indexing — the crawler
stores node labels + extracted tags in metadata but does NOT index full
file text for search".

Structure:
  _index:     word -> set[node_id]          (posting lists, AND-intersection)
  _doc_terms: node_id -> Counter(word)      (reverse map: O(doc-terms) removal
                                             + match-frequency sort in search)
  _sorted_terms: List[str]                 (Stage 20: maintained vocabulary,
                                             sorted for bisect-based prefix suggest)

Tokenization: regex \w+, lowercased, tokens shorter than 2 chars dropped.
No stemming, no stop-words, no phrase search. Stage 20 ADDS prefix
suggestion (bisect) and fuzzy AND-search (difflib) — both stdlib-only.

Architecture contract: stdlib only (re, collections, bisect, difflib) — a
strict subset of the allowed axis (contracts + stdlib). Never imports
adapters, kernel, cli, infrastructure or sibling services (enforced by
tests/test_architecture.py).
"""
from __future__ import annotations

import bisect
import difflib
import re
from collections import Counter
from typing import Any, Dict, List, Set

from contracts.snapshotable import ISnapshotable  # only new import (axis-clean)

_TOKEN_RE = re.compile(r"\w+")
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> List[str]:
    r"""\w+ tokens, lowercased, len >= 2. No stemming / stop-words."""
    return [
        t for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) >= _MIN_TOKEN_LEN
    ]


class ContentIndex(ISnapshotable):
    """In-memory inverted index: word -> posting list of node_ids."""

    def __init__(self) -> None:
        self._index: Dict[str, Set[str]] = {}
        self._doc_terms: Dict[str, Counter] = {}
        self._sorted_terms: List[str] = []  # Stage 20: sorted vocabulary

    # ----- internal: maintain sorted term list (Stage 20) -----
    def _rebuild_sorted_terms(self) -> None:
        self._sorted_terms = sorted(self._index.keys())

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
        self._rebuild_sorted_terms()

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
        self._rebuild_sorted_terms()

    # ----- Stage 20: prefix suggestion (for REPL autocomplete) -----
    def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """Return indexed terms starting with *prefix*, alphabetically (O(log V + k)).

        V = vocabulary size. Uses bisect_left to find the first term and walks
        forward while the prefix matches. Empty prefix or empty index -> [].
        """
        if not prefix or not self._sorted_terms:
            return []
        i = bisect.bisect_left(self._sorted_terms, prefix)
        out: List[str] = []
        n = len(self._sorted_terms)
        while i < n and self._sorted_terms[i].startswith(prefix):
            out.append(self._sorted_terms[i])
            if len(out) >= limit:
                break
            i += 1
        return out

    # ----- Stage 20: fuzzy AND-search -----
    def fuzzy_search(self, query: str, cutoff: float = 0.6) -> List[str]:
        """Fuzzy AND-search: each token is fuzzy-matched to indexed terms.

        cutoff: difflib SequenceMatcher ratio threshold (0.0–1.0, default 0.6).
        Each query token expands to up to 3 close matches (its own AND-group);
        the final result is the intersection across groups (a node must match at
        least one term in EACH group). Ranked by total matched-term frequency
        across all groups (same tiebreaker as exact search). Empty query or a
        token with no close match -> [].
        """
        tokens = _tokenize(query)
        if not tokens:
            return []

        groups: List[List[str]] = []
        for tok in tokens:
            close = difflib.get_close_matches(
                tok, self._sorted_terms, n=3, cutoff=cutoff
            )
            if not close:
                return []  # one token has no fuzzy candidate -> no results
            groups.append(close)

        result: Set[str] | None = None
        for group in groups:
            group_hits: Set[str] = set()
            for term in group:
                group_hits |= self._index.get(term, set())
            if not group_hits:
                return []
            result = group_hits if result is None else (result & group_hits)
            if not result:
                return []

        assert result is not None

        def _score(nid: str) -> tuple:
            score = 0
            for group in groups:
                score += sum(self._doc_terms[nid].get(term, 0) for term in group)
            return (-score, nid)

        return sorted(result, key=_score)

    def get_stats(self) -> Dict[str, int]:
        return {"terms": len(self._index), "documents": len(self._doc_terms)}

    # ----- Stage 19: ISnapshotable persistence (plain-dict, no file I/O) -----
    def snapshot(self) -> Dict[str, Any]:
        """Plain-dict for JSON serialization by an external store.

        Only dict/list/scalar primitives so any JSON encoder round-trips it.
        """
        return {
            "_index": {w: list(nodes) for w, nodes in self._index.items()},
            "_doc_terms": {nid: dict(cnt) for nid, cnt in self._doc_terms.items()},
        }

    def restore(self, data: Dict[str, Any]) -> None:
        """Full state replacement from a snapshot dict. O(terms + doc_terms)."""
        self._index = {
            w: set(nodes) for w, nodes in data.get("_index", {}).items()
        }
        self._doc_terms = {
            nid: Counter(cnt) for nid, cnt in data.get("_doc_terms", {}).items()
        }
        # Drop any posting lists that came back empty (defensive).
        self._index = {w: s for w, s in self._index.items() if s}
        # Stage 20: rebuild the sorted vocabulary so suggest()/fuzzy_search()
        # work after a cold restore from snapshot.
        self._rebuild_sorted_terms()
