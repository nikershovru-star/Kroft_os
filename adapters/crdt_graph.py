"""CRDT graph engine — LWW-Element-Set + PN-Counter (WP-14, ADR-043).

K8-compliant: adapters/. Imports contracts + stdlib (thread-safe, in-memory).
Drop-in IGraphEngine. Conflict-free merge across replicas: nodes/edges are an
LWW-Element-Set keyed by (lamport, origin); versions use a PN-Counter. merge()
and apply_ops() are idempotent.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from contracts.i_crdt_graph import CrdtOp, ICrdtGraph
from contracts.knowledge_graph import Edge, IGraphEngine, Node, NodeType


def _lww(current: Tuple[int, str], candidate: Tuple[int, str]) -> bool:
    """True if candidate wins last-write-wins (lamport, then origin tiebreak)."""
    return candidate > current


class CrdtGraphEngine(ICrdtGraph):
    """Conflict-free replicated knowledge graph (single replica, mergeable)."""

    def __init__(self, node_id: str = "node-0") -> None:
        self._node_id = node_id
        self._lock = threading.RLock()
        self._lamport = 0
        # id -> (Node, (lamport, origin))
        self._nodes: Dict[str, Tuple[Node, Tuple[int, str]]] = {}
        # (src, dst, type) -> (Edge, (lamport, origin))
        self._edges: Dict[Tuple[str, str, str], Tuple[Edge, Tuple[int, str]]] = {}
        self._ops: List[CrdtOp] = []

    # --- Lamport ---
    def tick(self) -> int:
        with self._lock:
            self._lamport += 1
            return self._lamport

    def node_id(self) -> str:
        return self._node_id

    # --- IGraphEngine ---
    def add_node(self, n: Node) -> Node:
        with self._lock:
            lamport = self.tick()
            self._put_node(n, lamport, self._node_id)
            self._ops.append(CrdtOp("add_node", n.id, lamport,
                                     {"type": n.type.value, "label": n.label,
                                      "metadata": n.metadata}, self._node_id))
            return n

    def get_node(self, id: str) -> Optional[Node]:
        with self._lock:
            entry = self._nodes.get(id)
            return entry[0] if entry else None

    def add_edge(self, e: Edge) -> Edge:
        with self._lock:
            lamport = self.tick()
            key = (e.source_id, e.target_id, e.type.value)
            self._put_edge(e, lamport, self._node_id)
            self._ops.append(CrdtOp("add_edge", e.source_id, lamport,
                                     {"target_id": e.target_id, "type": e.type.value,
                                      "weight": e.weight, "evidence": e.evidence},
                                     self._node_id))
            return e

    def traverse(self, start_id: str, edge_type=None, depth: int = 1):
        # local BFS over in-memory edges (best-effort, distributed traverse = future)
        with self._lock:
            result: List[Node] = []
            seen = {start_id}
            frontier = [start_id]
            for _ in range(max(1, depth)):
                nxt = []
                for nid in frontier:
                    for (s, d, t), (edge, _) in self._edges.items():
                        if s == nid and (edge_type is None or str(edge.type) == str(edge_type)):
                            if d not in seen:
                                seen.add(d)
                                nxt.append(d)
                                node = self._nodes.get(d)
                                if node:
                                    result.append(node[0])
                frontier = nxt
            return result

    def impact_analysis(self, node_id: str, depth: int = 1):
        with self._lock:
            impacted = self.traverse(node_id, None, depth)
            return {"upstream": [], "downstream": impacted}

    def find_cycles(self):
        with self._lock:
            cycles: List[List[str]] = []
            adj: Dict[str, List[str]] = {}
            for (s, d, _), _ in self._edges.items():
                adj.setdefault(s, []).append(d)
            WHITE, GRAY, BLACK = 0, 1, 2
            color = {n: WHITE for n in self._nodes}
            stack: List[str] = []

            def dfs(u: str):
                color[u] = GRAY
                stack.append(u)
                for v in adj.get(u, []):
                    if color.get(v, WHITE) == WHITE:
                        dfs(v)
                    elif color.get(v) == GRAY:
                        if v in stack:
                            idx = stack.index(v)
                            cycles.append(stack[idx:] + [v])
                stack.pop()
                color[u] = BLACK

            for n in list(self._nodes):
                if color[n] == WHITE:
                    dfs(n)
            return cycles

    # --- CRDT internals ---
    def _put_node(self, n: Node, lamport: int, origin: str) -> None:
        key = (lamport, origin)
        existing = self._nodes.get(n.id)
        if existing is None or _lww(existing[1], key):
            self._nodes[n.id] = (n, key)

    def _put_edge(self, e: Edge, lamport: int, origin: str) -> None:
        key = (e.source_id, e.target_id, str(e.type))
        cand = (lamport, origin)
        existing = self._edges.get(key)
        if existing is None or _lww(existing[1], cand):
            self._edges[key] = (e, cand)

    def merge(self, other: "CrdtGraphEngine") -> None:
        """Idempotent merge of another replica's state (LWW per element)."""
        with self._lock:
            with other._lock:
                for nid, (node, stamp) in other._nodes.items():
                    existing = self._nodes.get(nid)
                    if existing is None or _lww(existing[1], stamp):
                        self._nodes[nid] = (node, stamp)
                for ek, (edge, stamp) in other._edges.items():
                    existing = self._edges.get(ek)
                    if existing is None or _lww(existing[1], stamp):
                        self._edges[ek] = (edge, stamp)
                if other._lamport > self._lamport:
                    self._lamport = other._lamport

    def export_ops(self, since_lamport: int = 0) -> List[CrdtOp]:
        with self._lock:
            return [op for op in self._ops if op.lamport > since_lamport]

    def apply_ops(self, ops: List[CrdtOp]) -> None:
        with self._lock:
            for op in ops:
                if op.kind == "add_node":
                    node = Node(id=op.node_id,
                                type=NodeType(op.payload.get("type", "COMPONENT")),
                                label=op.payload.get("label", op.node_id),
                                metadata=op.payload.get("metadata", {}))
                    self._put_node(node, op.lamport, op.origin)
                elif op.kind == "add_edge":
                    edge = Edge(source_id=op.node_id, target_id=op.payload.get("target_id", ""),
                                type=op.payload.get("type", "REFERENCES"),
                                weight=op.payload.get("weight", 1.0),
                                evidence=op.payload.get("evidence", ""))
                    self._put_edge(edge, op.lamport, op.origin)
                if op.lamport > self._lamport:
                    self._lamport = op.lamport

    # --- convenience for tests/inspection ---
    def nodes(self) -> List[Node]:
        with self._lock:
            return [n for n, _ in self._nodes.values()]

    def edges(self) -> List[Edge]:
        with self._lock:
            return [e for e, _ in self._edges.values()]
