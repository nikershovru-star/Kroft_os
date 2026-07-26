"""In-memory graph builder implementation of IGraphBuilder."""
from __future__ import annotations
import copy
import json
import threading
from typing import Any, Dict, List

from contracts import IGraphBuilder


class InMemoryGraphBuilder(IGraphBuilder):
    """Thread-safe in-memory knowledge graph. get_graph() returns a deep copy."""

    def __init__(self) -> None:
        self._nodes: Dict[str, dict] = {}
        self._edges: List[dict] = []
        self._lock = threading.Lock()

    # ----- IService lifecycle -----
    def name(self) -> str:
        return "in_memory_graph_builder"

    def initialize(self, context: Any | None = None) -> None:
        # No external resources to acquire.
        return None

    def execute(self, context_data: dict) -> str | List[str]:
        g = self.get_graph()
        return f"nodes={len(g['nodes'])} edges={len(g['edges'])}"

    # ----- IGraphBuilder -----
    def add_node(self, id: str, label: str, meta: dict) -> None:
        with self._lock:
            self._nodes[id] = {"id": id, "label": label, "meta": dict(meta or {})}

    def add_edge(self, from_id: str, to_id: str, relation: str) -> None:
        with self._lock:
            self._edges.append({"from": from_id, "to": to_id, "relation": relation})

    def get_graph(self) -> dict:
        with self._lock:
            return {
                "nodes": copy.deepcopy(list(self._nodes.values())),
                "edges": copy.deepcopy(self._edges),
            }

    def get_neighbors(self, node_id: str) -> List[str]:
        with self._lock:
            return [e["to"] for e in self._edges if e["from"] == node_id]

    def clear(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._edges.clear()

    def remove_node(self, node_id: str) -> bool:
        """Remove `node_id` and all edges where it is either endpoint.

        Honest complexity note (Stage 17): O(edges) — the edge list is
        scanned linearly; there is no from/to index.
        """
        with self._lock:
            existed = node_id in self._nodes
            self._nodes.pop(node_id, None)
            self._edges = [
                e for e in self._edges
                if e["from"] != node_id and e["to"] != node_id
            ]
            return existed

    # ----- persistence (Stage 12) -----
    def snapshot(self, fs, path: str) -> None:
        """Serialize the whole graph to JSON via the IFileSystem port.

        Always a FULL snapshot (no incremental / no versioning): the single
        file at `path` is overwritten each call.
        """
        with self._lock:
            payload = {
                "nodes": {nid: dict(node) for nid, node in self._nodes.items()},
                "edges": [dict(e) for e in self._edges],
            }
        fs.write_content(path, json.dumps(payload, ensure_ascii=False))

    def restore(self, fs, path: str) -> bool:
        """Load the graph from JSON via IFileSystem.

        Returns True on success. On missing file or corrupt JSON, returns
        False and leaves the graph EMPTY (silent fallback, no exception leaks).
        """
        if not fs.exists(path):
            return False
        try:
            raw = fs.read_content(path)
            data = json.loads(raw)
            nodes = data.get("nodes", {})
            edges = data.get("edges", [])
        except Exception:
            return False
        with self._lock:
            self._nodes = {
                str(nid): {
                    "id": str(n.get("id", nid)),
                    "label": n.get("label", str(nid)),
                    "meta": dict(n.get("meta") or {}),
                }
                for nid, n in nodes.items()
            }
            self._edges = [
                {
                    "from": e.get("from"),
                    "to": e.get("to"),
                    "relation": e.get("relation", "links_to"),
                }
                for e in edges
                if e.get("from") is not None
            ]
        return True
