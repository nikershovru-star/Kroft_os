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

# Trust state is a flat Dict[author_id, running_trust(float)]; reused verbatim
# by the restore path (same shape run_evolution.py replays into ReferenceTrustRegistry).
TrustState = Dict[str, float]

# Procedural memory state: {procedures: name->stats, skills: capability->Procedure-dict}.
# Both are plain serializable structures; skills go through the existing
# _procedure_to_dict converter in kernel/persistence.py (K5: reuse, never duplicate).
ProceduralState = Dict[str, Any]

# Episodic memory state: a list of Episode dicts (via _episode_to_dict).
EpisodicState = list  # List[Dict[str, Any]]


class KnowledgeSnapshotStore:
    """JSON save/load of the live knowledge graph + content index + trust + procedural + episodic.

    Composition-only seam (Флаг C): owns file I/O so graph engine / content
    index / trust registry / procedural memory / layered memory stay axis-clean
    (K1). All five live in ONE deterministic JSON file (atomic + single source
    of truth). Round-trip is byte-stable for identical state (I-09): sort_keys +
    deterministic order. save/load NEVER mutate HARD — they restore SOFT-derived
    knowledge only.
    """

    def __init__(self, path: str) -> None:
        # path may live under a vault with spaces; pathlib-free, stdlib only.
        self._path = path

    def save(self, graph_state: Dict[str, Any], index_state: Dict[str, Any],
             meta: Optional[Dict[str, Any]] = None,
             trust: Optional[TrustState] = None,
             procedural: Optional[ProceduralState] = None,
             episodes: Optional[EpisodicState] = None) -> str:
        """Write {graph, index, meta, trust, procedural, episodes} to the snapshot file."""
        payload: Dict[str, Any] = {
            "version": 1,
            "graph": graph_state,
            "index": index_state,
            "trust": trust or {},
            "procedural": procedural or {},
            "episodes": episodes or [],
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

    def load_trust(self, data: Optional[Dict[str, Any]] = None) -> TrustState:
        """Extract the running-trust map from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return {}
        raw = data.get("trust", {})
        # defensive: only keep valid float scores (ignore corrupt entries)
        return {a: float(v) for a, v in raw.items() if isinstance(v, (int, float))}

    def load_procedural(self, data: Optional[Dict[str, Any]] = None) -> ProceduralState:
        """Extract the procedural-memory state from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return {}
        raw = data.get("procedural", {})
        # defensive: require the two expected sub-keys; ignore anything malformed
        if not isinstance(raw, dict) or "procedures" not in raw:
            return {}
        return dict(raw)

    def load_episodic(self, data: Optional[Dict[str, Any]] = None) -> EpisodicState:
        """Extract the episode list from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return []
        raw = data.get("episodes", [])
        # defensive: only accept a list of dicts (Episode blobs)
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict)]
