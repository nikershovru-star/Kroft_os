"""Knowledge persistence layer (ТЗ-KNOWLEDGE-PERSIST-01, Флаг C).

Composition-only seam: owns file I/O so the graph engine + content index stay
axis-clean (K1). Saves the LIVE knowledge graph (InMemoryGraphEngine) + the
inverted content index (ContentIndex, ISnapshotable) into one deterministic
JSON file, and restores it on a cold boot so KROFT_OS starts "already learned"
from the vault instead of re-reading every markdown file.

Stdlib-only (json). Round-trip is byte-stable for identical state (I-09):
sort_keys + deterministic field order. save/load NEVER mutate HARD — they only
restore SOFT-derived knowledge (graph nodes/edges + inverted index terms).

Restore semantics are MERGE-friendly: a caller may restore a snapshot BEFORE
ingesting the live vault, so on-disk knowledge is reused and only NEW notes are
added (idempotent ingestion in KnowledgeEngine keeps it consistent). When no
snapshot exists yet, load returns empty state (graceful — first run).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


class KnowledgeSnapshotStore:
    """JSON save/load of the live knowledge graph + content index."""

    def __init__(self, path: str) -> None:
        # path may live under a vault with spaces; pathlib-free, stdlib only.
        self._path = path

    def save(self, graph_state: Dict[str, Any], index_state: Dict[str, Any],
             meta: Optional[Dict[str, Any]] = None) -> str:
        """Write {graph, index, meta} to the snapshot file. Returns the path."""
        payload: Dict[str, Any] = {
            "version": 1,
            "graph": graph_state,
            "index": index_state,
            "meta": meta or {},
        }
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        return self._path

    def load(self) -> Optional[Dict[str, Any]]:
        """Load a snapshot dict, or None when the file is missing (graceful)."""
        if not os.path.isfile(self._path):
            return None
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return None  # corrupt snapshot -> treat as missing (graceful degrade)
        return data
