"""PHASE B.2 — Multi-Resolution Query service (ТЗ Фаза 2, separate service).

Reuse-first, K6-compliant (services -> contracts + stdlib + sibling services).
This is a THIN wrapper over the existing ``GraphQueryEngine`` (sibling-owned file,
NOT modified here per ТЗ §35) that adds the semantic-ladder navigation API:

    nodes_by_level(level)  -> all node ids at observation|fact|pattern|concept
    zoom_in(node_id)       -> child (more detailed) nodes via level edges
    zoom_out(node_id)      -> parent (more abstract) nodes via level edges
    add_level_relation(...) -> establish a semantic edge child->parent
    get_level(node_id)     -> semantic level of a node

It reuses GraphQueryEngine._type_of / _meta_of / get_neighbors(edge_types=...) and
the backing IGraphBuilder (add_edge). No new storage, no LLM, no nx required.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contracts.igraph_builder import IGraphBuilder
from services.graph_query_engine import GraphQueryEngine


class MultiResolutionQuery:
    """Semantic-ladder navigation over a GraphQueryEngine + its IGraphBuilder."""

    # Edge types carrying semantic-abstraction direction (child -> parent).
    _LEVEL_CHILD_TO_PARENT = ("has_part", "derived_from", "aggregates", "supported_by")

    def __init__(self, engine: GraphQueryEngine, builder: IGraphBuilder) -> None:
        self._q = engine
        self._b = builder

    # -- level resolution (mirrors contracts.knowledge_graph.get_level) --
    @staticmethod
    def _level_of(node: Dict[str, Any]) -> Optional[str]:
        t = node.get("type")
        if t in ("OBSERVATION", "FACT", "PATTERN", "CONCEPT"):
            return str(t).lower()
        meta = node.get("meta") or node.get("metadata") or {}
        lvl = meta.get("level") if isinstance(meta, dict) else None
        return str(lvl).lower() if lvl else None

    def get_level(self, node_id: str) -> Optional[str]:
        n = self._q._find_node(node_id)
        return self._level_of(n) if n else None

    def nodes_by_level(self, level: str) -> List[str]:
        """All node ids at the given semantic level (observation|fact|pattern|concept)."""
        want = str(level).lower()
        return [n["id"] for n in self._q._snapshot()["nodes"]
                if self._level_of(n) == want]

    def zoom_in(self, node_id: str) -> List[str]:
        """Child nodes (more detailed): edges where `node_id` is the PARENT.

        Semantic edges are stored child->parent (fact --aggregates--> pattern).
        A child (more detailed) is reached by following the edge INWARD to
        `node_id`. Per ТЗ Фаза 2 direction Concept -> Pattern -> Fact -> Observation.
        """
        return [d["id"] for d in self._q.get_neighbors(
            node_id, direction="in", edge_types=list(self._LEVEL_CHILD_TO_PARENT))]

    def zoom_out(self, node_id: str) -> List[str]:
        """Parent nodes (more abstract): edges where `node_id` is the CHILD."""
        return [d["id"] for d in self._q.get_neighbors(
            node_id, direction="out", edge_types=list(self._LEVEL_CHILD_TO_PARENT))]

    def add_level_relation(self, child_id: str, parent_id: str,
                           relation_type: str = "aggregates") -> None:
        """Establish a semantic-level edge child->parent (ТЗ Фаза 2 / Фаза 3).

        Writes through to the backing IGraphBuilder so Self-Evolution can build
        the ladder. The builder de-duplicates edges.
        """
        self._b.add_edge(child_id, parent_id, relation_type)
