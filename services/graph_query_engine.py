"""Graph Query Engine -- second application-layer IService.

Read-only structural queries over a knowledge graph owned by an IGraphBuilder.
Depends ONLY on contracts.* (+ stdlib); it never imports adapters,
infrastructure, kernel, or runtime.

Service-to-service communication: VaultStreamCrawler WRITES to a shared
IGraphBuilder instance; GraphQueryEngine READS from the SAME instance. The two
services never reference each other -- they are coupled only through the
contracts.IGraphBuilder / contracts.IGraphQuery ports.
"""
from __future__ import annotations
from collections import deque
from typing import Any, Dict, List, Optional

from contracts import IService, IGraphBuilder, IGraphQuery


class GraphQueryEngine(IGraphQuery):
    """Pure read-only structural query engine over a shared IGraphBuilder."""

    def __init__(self, graph: IGraphBuilder) -> None:
        # Snapshot-on-read: every query pulls a fresh deep-copy snapshot via
        # graph.get_graph(), so the crawler may mutate the live graph (add
        # nodes/edges) between our calls without corrupting an in-flight query.
        self._graph = graph

    # ----- IService -----
    def name(self) -> str:
        return "graph_query_engine"

    def initialize(self, context: Any | None = None) -> None:
        return None

    def execute(self, context_data: dict) -> str | List[str]:
        # Convenience entry: return the live stats summary string.
        s = self.stats()
        return (
            f"nodes={s['total_nodes']} edges={s['total_edges']} "
            f"orphans={s['orphan_count']}"
        )

    # ----- helpers (operate on a snapshot dict) -----
    @staticmethod
    def _tags_of(node: dict) -> List[str]:
        meta = node.get("meta") or {}
        tags = meta.get("tags") or []
        return list(tags)

    def _snapshot(self) -> dict:
        return self._graph.get_graph()

    # ----- IGraphQuery -----
    def backlinks(self, node_id: str) -> List[str]:
        g = self._snapshot()
        seen: Dict[str, None] = {}
        for e in g["edges"]:
            if e.get("to") == node_id:
                seen.setdefault(e.get("from"), None)
        return list(seen.keys())

    def forward_links(self, node_id: str) -> List[str]:
        g = self._snapshot()
        seen: Dict[str, None] = {}
        for e in g["edges"]:
            if e.get("from") == node_id:
                seen.setdefault(e.get("to"), None)
        return list(seen.keys())

    def nodes_by_tag(self, tag: str) -> List[str]:
        g = self._snapshot()
        return [n["id"] for n in g["nodes"] if tag in self._tags_of(n)]

    def orphan_nodes(self) -> List[str]:
        g = self._snapshot()
        connected: set = set()
        for e in g["edges"]:
            connected.add(e.get("from"))
            connected.add(e.get("to"))
        return [n["id"] for n in g["nodes"] if n["id"] not in connected]

    def path(self, from_id: str, to_id: str, max_depth: int = 10) -> Optional[List[str]]:
        if max_depth < 0:
            return None
        g = self._snapshot()
        # adjacency (directed forward edges only)
        adj: Dict[str, List[str]] = {}
        for n in g["nodes"]:
            adj.setdefault(n["id"], [])
        for e in g["edges"]:
            f = e.get("from")
            t = e.get("to")
            if f is not None:
                adj.setdefault(f, []).append(t)
        if from_id not in adj or to_id not in adj:
            return None
        if from_id == to_id:
            return [from_id]
        # BFS for shortest path
        queue: "deque[str]" = deque([from_id])
        visited = {from_id}
        parent: Dict[str, Optional[str]] = {from_id: None}
        depth = {from_id: 0}
        while queue:
            cur = queue.popleft()
            if cur == to_id:
                # reconstruct
                path: List[str] = []
                node: Optional[str] = cur
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return path
            if depth[cur] >= max_depth:
                continue
            for nxt in adj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    parent[nxt] = cur
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
        return None

    def cluster_by_tag(self) -> Dict[str, List[str]]:
        g = self._snapshot()
        clusters: Dict[str, List[str]] = {}
        for n in g["nodes"]:
            for tag in self._tags_of(n):
                clusters.setdefault(tag, []).append(n["id"])
        return clusters

    def stats(self) -> Dict[str, object]:
        g = self._snapshot()
        total_nodes = len(g["nodes"])
        total_edges = len(g["edges"])
        avg_degree = (total_edges / total_nodes) if total_nodes else 0.0
        orphan_count = len(self.orphan_nodes())
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "avg_degree": avg_degree,
            "orphan_count": orphan_count,
        }
