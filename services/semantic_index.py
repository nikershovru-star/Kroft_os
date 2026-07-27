"""SemanticIndex — dense-vector nearest-neighbour search (Stage 29).

Brute-force cosine similarity, O(nodes) per query — honest for vault-scale
(hundreds of notes); thousands would need FAISS/ANN (external dep, out of
the arch gate).

Implements the ISnapshotable protocol (snapshot()/restore()) so the Kernel
persists it to data/semantic_snapshot.json exactly like ContentIndex
(Stage 19 convention) — without importing this class (axis-clean).

Arch: services/ imports contracts + stdlib only (here: math + typing).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


class SemanticIndex:
    """In-memory {node_id: embedding} store with cosine top-k search."""

    def __init__(self, embedding_dim: int = 128) -> None:
        self._dim = embedding_dim
        self._index: Dict[str, List[float]] = {}

    def __len__(self) -> int:
        return len(self._index)

    def add(self, node_id: str, embedding: List[float]) -> None:
        self._index[node_id] = list(embedding)

    def remove(self, node_id: str) -> None:
        self._index.pop(node_id, None)

    def search(self, query_embedding: List[float], top_k: int = 10) -> List[Tuple[str, float]]:
        """Top-k (node_id, cosine) pairs, best first. Zero-vector query -> []."""
        if not self._index or top_k <= 0:
            return []
        q_norm = math.sqrt(sum(v * v for v in query_embedding))
        if q_norm == 0:
            return []
        q_unit = [v / q_norm for v in query_embedding]
        scores: List[Tuple[str, float]] = []
        for nid, emb in self._index.items():
            e_norm = math.sqrt(sum(v * v for v in emb))
            if e_norm == 0:
                continue
            sim = sum(a * b for a, b in zip(q_unit, emb)) / e_norm
            scores.append((nid, sim))
        # Deterministic tie-break: score desc, then node id asc.
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores[:top_k]

    # ----- ISnapshotable -----
    def snapshot(self) -> Dict[str, Any]:
        return {k: list(v) for k, v in self._index.items()}

    def restore(self, data: Dict[str, Any]) -> None:
        self._index = {k: list(v) for k, v in (data or {}).items()}
