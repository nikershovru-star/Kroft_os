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
             episodes: Optional[EpisodicState] = None,
             semantic: Optional[list] = None,
             normative: Optional[list] = None,
             semantic_vectors: Optional[Dict[str, list]] = None,
             destructive: bool = False) -> str:
        """Write {graph, index, meta, trust, procedural, episodes, semantic, normative, semantic_vectors}.

        SAFETY (ТЗ P0 recovery, Этап 9): a caller that forgets to pass
        ``semantic_vectors`` (e.g. a broad pytest that re-snapshots an empty
        kernel) MUST NOT wipe the 16k+ foundation vectors already on disk.
        When ``semantic_vectors`` is empty/None and the on-disk snapshot
        already carries vectors, we transparently preserve them UNLESS
        ``destructive=True`` is explicitly passed. This is a minimal guard on
        the existing component — no new layer, no signature break for the two
        real callers (run_kroft._save_knowledge, foundation_ingest.build) which
        both pass ``semantic_vectors`` explicitly.
        """
        sv = semantic_vectors
        if not sv and not destructive and os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as _fh:
                    _existing = json.load(_fh).get("semantic_vectors", {}) or {}
                if _existing:
                    sv = _existing
            except Exception:
                pass
        payload: Dict[str, Any] = {
            "version": 1,
            "graph": graph_state,
            "index": index_state,
            "trust": trust or {},
            "procedural": procedural or {},
            "episodes": episodes or [],
            "semantic": semantic or [],
            "semantic_vectors": sv or {},
            "normative": normative or [],
            "meta": meta or {},
        }
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # Atomic write (ТЗ-L10.7): never replace the canonical snapshot with a
        # partially-written file. Write to a sibling .tmp, fsync, then os.replace
        # (atomic rename on POSIX/Windows). On crash mid-write only the .tmp is
        # left behind; the original remains valid.
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)
        return self._path

    def load(self) -> Optional[Dict[str, Any]]:
        """Load a snapshot dict, or None when the file is missing (graceful)."""
        if not os.path.isfile(self._path):
            return None
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            # Corruption detected: preserve the broken file as .corrupt for manual
            # recovery instead of silently destroying it (minimal scope — no backup
            # system). The runtime then degrades gracefully from empty state.
            _corrupt = self._path + ".corrupt"
            try:
                if os.path.isfile(_corrupt):
                    os.remove(_corrupt)
                os.replace(self._path, _corrupt)
            except Exception:
                pass
            return None
        except Exception:
            return None  # other read error -> graceful degrade
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

    def load_semantic(self, data: Optional[Dict[str, Any]] = None) -> list:
        """Extract the semantic-fact list from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return []
        raw = data.get("semantic", [])
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict)]

    def load_normative(self, data: Optional[Dict[str, Any]] = None) -> list:
        """Extract the normative-policy list from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return []
        raw = data.get("normative", [])
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict)]

    def load_semantic_vectors(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, list]:
        """Extract the id->vector map from a loaded snapshot (graceful empty)."""
        if data is None:
            data = self.load()
        if not data:
            return {}
        raw = data.get("semantic_vectors", {})
        if not isinstance(raw, dict):
            return {}
        return {k: list(v) for k, v in raw.items() if isinstance(v, list)}
