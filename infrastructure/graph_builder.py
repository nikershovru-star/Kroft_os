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
            m = dict(meta or {})
            # Stage 44: guarantee meta["tags"] is a list
            if "tags" not in m or not isinstance(m["tags"], list):
                m["tags"] = list(m.get("tags", [])) if isinstance(m.get("tags"), list) else []
            self._nodes[id] = {"id": id, "label": label, "meta": m}

    def add_edge(self, from_id: str, to_id: str, relation: str) -> None:
        """Append an edge; idempotent (Stage 44): duplicate (from,to) skipped."""
        with self._lock:
            for e in self._edges:
                if e["from"] == from_id and e["to"] == to_id:
                    return  # already present
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

    def remove_edge(self, from_id: str, to_id: str) -> bool:
        """Remove a single edge (from_id -> to_id) if present (Stage 44)."""
        with self._lock:
            new_edges = [
                e for e in self._edges
                if not (e["from"] == from_id and e["to"] == to_id)
            ]
            removed = len(new_edges) != len(self._edges)
            self._edges = new_edges
            return removed

    def add_tag(self, node_id: str, tag: str) -> bool:
        """Append `tag` to node meta["tags"] (unique). Returns added (Stage 44)."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            tags = node["meta"].setdefault("tags", [])
            if not isinstance(tags, list):
                tags = []
                node["meta"]["tags"] = tags
            if tag in tags:
                return False
            tags.append(tag)
            return True

    def remove_tag(self, node_id: str, tag: str) -> bool:
        """Remove `tag` from node meta["tags"]. Returns removed (Stage 44)."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            tags = node["meta"].get("tags")
            if not isinstance(tags, list) or tag not in tags:
                return False
            tags.remove(tag)
            return True

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
        # Atomic write: temp file then rename onto the target (overwrite-safe).
        tmp = path + ".tmp"
        fs.write_content(tmp, json.dumps(payload, ensure_ascii=False))
        if hasattr(fs, "rename"):
            fs.rename(tmp, path)  # type: ignore[attr-defined]
        else:  # pragma: no cover - ports without rename
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

    def load_from_dict(self, nodes: Dict[str, dict], edges: List[dict]) -> None:
        """Load pre-parsed snapshot data into the builder (Foundation bridge).

        Unlike restore() (which reads a file and DROPS the node ``type`` field),
        this preserves ``type`` so Multi-Resolution ``nodes_by_type()`` works on
        production snapshots that carry a top-level ``"type"`` (e.g. "unknown"),
        not a Node dataclass. Used by the boot-bridge in container_builder.py to
        make the Query API see Foundation nodes (ADR-033).

        Does NOT clear existing nodes first — runtime nodes (handoff, promoted
        facts) are preserved; only absent ids are added (idempotent merge).
        """
        with self._lock:
            for nid, n in nodes.items():
                if nid in self._nodes:
                    continue  # keep existing runtime node on id collision
                self._nodes[str(nid)] = {
                    "id": str(n.get("id", nid)),
                    "label": n.get("label", str(nid)),
                    "type": n.get("type"),  # preserve production type
                    "meta": dict(n.get("meta") or {}),
                }
            _seen = {(e.get("from"), e.get("to")) for e in self._edges}
            for e in edges:
                f = e.get("from") or e.get("source_id")
                t = e.get("to") or e.get("target_id")
                if f is None or t is None:
                    continue
                if (f, t) in _seen:
                    continue
                self._edges.append({
                    "from": f,
                    "to": t,
                    "relation": e.get("relation") or e.get("type") or "links_to",
                })
                _seen.add((f, t))
