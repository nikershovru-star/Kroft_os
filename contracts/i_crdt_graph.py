"""CRDT graph port (WP-14, ADR-043, RFC-014).

K1-compliant: stdlib only. Extends IGraphEngine (drop-in). Adds CRDT merge /
op-export / op-apply for conflict-free replication across nodes. KG nodes/edges
are an LWW-Element-Set keyed by (lamport, node_id); versions use a PN-Counter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CrdtOp:
    """A single replicated graph mutation."""
    kind: str            # "add_node" | "add_edge" | "touch"
    node_id: str
    lamport: int
    payload: Dict[str, Any] = field(default_factory=dict)
    origin: str = ""     # node id that produced the op


class ICrdtGraph(ABC):
    """CRDT-aware graph: IGraphEngine + conflict-free merge."""

    # --- IGraphEngine surface (re-declared for clarity; impls provide them) ---
    def add_node(self, n):  # pragma: no cover - interface
        raise NotImplementedError

    def get_node(self, id: str):  # pragma: no cover
        raise NotImplementedError

    def add_edge(self, e):  # pragma: no cover
        raise NotImplementedError

    def traverse(self, start_id: str, edge_type=None, depth: int = 1):  # pragma: no cover
        raise NotImplementedError

    def impact_analysis(self, node_id: str, depth: int = 1):  # pragma: no cover
        raise NotImplementedError

    def find_cycles(self):  # pragma: no cover
        raise NotImplementedError

    # --- CRDT surface ---
    @abstractmethod
    def tick(self) -> int:
        """Advance and return the local Lamport clock."""

    @abstractmethod
    def merge(self, other: "ICrdtGraph") -> None:
        """Idempotent CRDT merge of another node's state into this one."""

    @abstractmethod
    def export_ops(self, since_lamport: int = 0) -> List[CrdtOp]:
        """Return ops with lamport > since_lamport (for sync)."""

    @abstractmethod
    def apply_ops(self, ops: List[CrdtOp]) -> None:
        """Apply remote ops (LWW per node/edge)."""

    @abstractmethod
    def node_id(self) -> str:
        """This replica's node id (for LWW tiebreak + op.origin)."""
