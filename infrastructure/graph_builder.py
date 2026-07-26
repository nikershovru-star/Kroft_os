"""In-memory graph builder implementation of IGraphBuilder."""
from __future__ import annotations
import copy
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
