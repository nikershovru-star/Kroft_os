"""InMemoryMemoryStore — dict-backed IMemoryStore (Wave 9, ADR-012 Phase C).

v0.1 engine. The whole point of ADR-012 is that this class is replaceable:
SQLite (v0.5) and a vector store (v1.0) implement the same port and nothing in
`services/` changes.

Thread-safety: this implementation IS lock-guarded (the port itself promises
nothing — see ADR-012 §2.3). A `threading.Lock` is cheap here and the store is
shared between the Router path and consolidation.

TTL is LAZY (ADR-012 §3): an expired item stops being *visible* through
get()/query() immediately, and is *physically* removed only by an explicit
delete_expired(). "Expired" and "deleted" stay distinguishable and observable —
no background thread, no cron (stdlib-first).
"""
from __future__ import annotations

import fnmatch
import threading
import time
from typing import Dict, List, Optional

from contracts.i_memory import IMemoryStore, MemoryItem, MemoryQuery


class InMemoryMemoryStore(IMemoryStore):
    """Process-local memory store. Explicit state object (LAW 3: no globals)."""

    def __init__(self) -> None:
        self._items: Dict[str, MemoryItem] = {}
        self._lock = threading.Lock()
        # LAW 5: cheap counters so callers can measure what the store did
        self.stats: Dict[str, int] = {"put": 0, "expired": 0, "compressed": 0}

    # --- IMemoryStore ------------------------------------------------------
    def put(self, item: MemoryItem) -> None:
        with self._lock:
            self._items[item.key] = item
            self.stats["put"] += 1

    def get(self, key: str) -> Optional[MemoryItem]:
        with self._lock:
            item = self._items.get(key)
        if item is None or item.is_expired():
            return None
        return item

    def query(self, q: MemoryQuery) -> List[MemoryItem]:
        now = time.time()
        with self._lock:
            candidates = list(self._items.values())

        out = [i for i in candidates if not i.is_expired(now) and self._matches(i, q, now)]
        # Newest first — the Router wants the most recent turns.
        # Tie-break on key: the clock resolution on Windows is ~15ms, so several
        # items written in the same instant share a timestamp and a pure
        # timestamp sort would return them in arbitrary order. Keys carry a
        # zero-padded monotonic sequence (`session:<id>:000007`), so descending
        # key order restores true insertion order within one tick.
        out.sort(key=lambda i: (i.timestamp, i.key), reverse=True)
        if q.limit is not None and q.limit >= 0:
            out = out[: q.limit]
        return out

    def delete_expired(self) -> int:
        now = time.time()
        with self._lock:
            expired = [k for k, i in self._items.items() if i.is_expired(now)]
            for k in expired:
                del self._items[k]
            self.stats["expired"] += len(expired)
        return len(expired)

    def compress(self, threshold: float = 0.3) -> int:
        """Drop low-importance items. Returns the count (LAW 5: measure it).

        v0.1 is deletion, not summarisation — the ADR is explicit that
        LLM-based compression is v1.0.
        """
        with self._lock:
            doomed = [k for k, i in self._items.items() if i.importance < threshold]
            for k in doomed:
                del self._items[k]
            self.stats["compressed"] += len(doomed)
        return len(doomed)

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _matches(item: MemoryItem, q: MemoryQuery, now: float) -> bool:
        if q.key_pattern and not fnmatch.fnmatch(item.key, q.key_pattern):
            return False
        if q.tags and not item.has_tags(q.tags):
            return False
        if q.min_importance is not None and item.importance < q.min_importance:
            return False
        if q.time_range:
            start, end = q.time_range
            if not (start <= item.timestamp <= end):
                return False
        if q.semantic_query:
            # exact-store fallback: substring match. Real ranking lives in
            # ISemanticMemory implementations, not here.
            if q.semantic_query.lower() not in item.content.lower():
                return False
        return True

    # --- introspection (tests / observability) -----------------------------
    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._items.keys())
