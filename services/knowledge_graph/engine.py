"""In-memory knowledge graph engine (TZ-KNOW-001 WP-02, ADR-036).
K1-compliant: imports ONLY contracts.knowledge_graph + stdlib. Thread-safe
(RLock). O(1) node lookup, adjacency + reverse adjacency for impact analysis,
DFS cycle detection (color marking).
"""
from __future__ import annotations
from threading import RLock
from typing import Any, Dict, List, Optional
from contracts.knowledge_graph import (
    Edge,
    EdgeType,
    IGraphEngine,
    Node,
    NodeType,
)

class InMemoryGraphEngine(IGraphEngine):
    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._out: Dict[str, List[Edge]] = {}
        self._in: Dict[str, List[Edge]] = {}
        self._lock = RLock()

    def add_node(self, n: Node) -> Node:
        with self._lock:
            self._nodes[n.id] = n
            self._out.setdefault(n.id, [])
            self._in.setdefault(n.id, [])
            return n

    def get_node(self, id: str) -> Optional[Node]:
        with self._lock:
            return self._nodes.get(id)

    def add_edge(self, e: Edge) -> Edge:
        with self._lock:
            if e.source_id not in self._nodes or e.target_id not in self._nodes:
                raise KeyError("both endpoints must exist before adding an edge")
            existing = {x.id for x in self._out[e.source_id]}
            if e.id not in existing:
                self._out[e.source_id].append(e)
                self._in[e.target_id].append(e)
            return e

    def traverse(self, start_id: str, edge_type: Optional[EdgeType],
                 depth: int) -> List[Node]:
        with self._lock:
            if start_id not in self._nodes:
                return []
            visited: Dict[str, Node] = {}
            frontier = [start_id]
            for _ in range(max(depth, 1)):
                nxt = []
                for nid in frontier:
                    for e in self._out.get(nid, []):
                        if edge_type is None or e.type == edge_type:
                            if e.target_id not in visited:
                                visited[e.target_id] = self._nodes[e.target_id]
                                nxt.append(e.target_id)
                frontier = nxt
            return list(visited.values())

    def impact_analysis(self, node_id: str, depth: int) -> Dict[str, List[Node]]:
        """Nodes that depend on node_id (reverse edges), grouped by NodeType."""
        with self._lock:
            if node_id not in self._nodes:
                return {}
            affected: Dict[str, Node] = {}
            frontier = [node_id]
            for _ in range(max(depth, 1)):
                nxt = []
                for nid in frontier:
                    for e in self._in.get(nid, []):
                        if e.source_id not in affected:
                            affected[e.source_id] = self._nodes[e.source_id]
                            nxt.append(e.source_id)
                frontier = nxt
            grouped: Dict[str, List[Node]] = {}
            for n in affected.values():
                grouped.setdefault(n.type.value, []).append(n)
            return grouped

    def find_cycles(self) -> List[List[str]]:
        """DFS color-marking (white/gray/black). Returns list of cycle paths."""
        with self._lock:
            WHITE, GRAY, BLACK = 0, 1, 2
            color = {nid: WHITE for nid in self._nodes}
            cycles: List[List[str]] = []
            path: List[str] = []

            def dfs(nid: str) -> None:
                color[nid] = GRAY
                path.append(nid)
                for e in self._out.get(nid, []):
                    tid = e.target_id
                    if color.get(tid, BLACK) == GRAY:
                        cycle_start = path.index(tid)
                        cycles.append(path[cycle_start:] + [tid])
                    elif color.get(tid, BLACK) == WHITE:
                        dfs(tid)
                path.pop()
                color[nid] = BLACK

            for nid in self._nodes:
                if color[nid] == WHITE:
                    dfs(nid)
            return cycles

    def nodes(self) -> List[Node]:
        with self._lock:
            return list(self._nodes.values())

    def edges(self) -> List[Edge]:
        with self._lock:
            return [e for lst in self._out.values() for e in lst]

    # ---- Stage 49: snapshot persistence (ТЗ-KNOWLEDGE-PERSIST-01) ----
    # K1-compliant: returns/loads a plain-dict; this method NEVER touches the
    # filesystem (an external SnapshotStore owns file I/O). Round-trip is
    # byte-stable for identical state (I-09).
    def snapshot(self) -> Dict[str, Any]:
        """Serialize nodes + edges to a JSON-friendly plain-dict."""
        with self._lock:
            nodes = [
                {
                    "id": n.id,
                    "type": n.type.value,
                    "label": n.label,
                    "metadata": dict(n.metadata),
                    "version": n.version,
                    "created_at": n.created_at,
                    "modified_at": n.modified_at,
                    "tenant_id": n.tenant_id,
                }
                for n in self._nodes.values()
            ]
            edges = [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "type": e.type.value if isinstance(e.type, EdgeType) else str(e.type),
                    "weight": e.weight,
                    "evidence": e.evidence,
                }
                for e in self.edges()
            ]
            return {"nodes": nodes, "edges": edges}

    def restore(self, data: Dict[str, Any]) -> None:
        """Wholesale state replacement from a snapshot dict (O(nodes + edges))."""
        with self._lock:
            self._nodes = {}
            self._out = {}
            self._in = {}
            for nd in data.get("nodes", []):
                node = Node(
                    id=nd["id"],
                    type=NodeType(nd["type"]),
                    label=nd["label"],
                    metadata=dict(nd.get("metadata", {})),
                    version=nd.get("version", 1),
                    created_at=nd.get("created_at", ""),
                    modified_at=nd.get("modified_at", ""),
                    tenant_id=nd.get("tenant_id", "default"),
                )
                self._nodes[node.id] = node
                self._out.setdefault(node.id, [])
                self._in.setdefault(node.id, [])
            for ed in data.get("edges", []):
                edge = Edge(
                    source_id=ed["source_id"],
                    target_id=ed["target_id"],
                    type=ed["type"],
                    weight=ed.get("weight", 1.0),
                    evidence=ed.get("evidence", ""),
                )
                # edges whose endpoints are missing are dropped (defensive, idempotent)
                if edge.source_id in self._nodes and edge.target_id in self._nodes:
                    self._out[edge.source_id].append(edge)
                    self._in[edge.target_id].append(edge)
