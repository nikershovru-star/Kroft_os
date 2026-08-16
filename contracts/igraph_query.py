"""Graph query port (Hexagonal Architecture).

A service-style port: it expresses an application capability (querying a
knowledge graph) and therefore inherits IService. Concrete implementations
(e.g. GraphQueryEngine) are injected via the DI container and operate on a
shared IGraphBuilder instance -- this is how two application services
(VaultStreamCrawler writing, GraphQueryEngine reading) communicate WITHOUT
a direct dependency on each other.
"""
from __future__ import annotations
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from .i_service import IService


class IGraphQuery(IService):
    """Port for read-only structural queries over a knowledge graph."""

    @abstractmethod
    def backlinks(self, node_id: str) -> List[str]:
        """Return ids of nodes that link TO node_id (incoming edges)."""

    @abstractmethod
    def forward_links(self, node_id: str) -> List[str]:
        """Return ids of nodes that node_id links TO (outgoing edges)."""

    @abstractmethod
    def nodes_by_tag(self, tag: str) -> List[str]:
        """Return ids of all nodes carrying the given tag."""

    @abstractmethod
    def nodes_by_type(self, node_type: str) -> List[str]:
        """Multi-Resolution (B.5/B.9): all node ids whose type == node_type.

        Reads node["type"] (production/foundation shape) OR node["meta"]["type"]
        (runtime builder shape) — robust to both serialization forms.
        """

    @abstractmethod
    def nodes_by_metadata(self, key: str, value: Optional[Any] = None) -> List[str]:
        """Multi-Resolution (B.5/B.9): all node ids carrying `key` in metadata.

        Reads node["meta"] / node["metadata"] (both shapes). If `value` is given,
        only nodes whose metadata[key] == value match; otherwise any presence.
        Example: nodes_by_metadata("level", "concept") or nodes_by_metadata("evidence_refs").
        """

    @abstractmethod
    def orphan_nodes(self) -> List[str]:
        """Return ids of nodes with NO edges (in-degree 0 AND out-degree 0)."""

    @abstractmethod
    def path(self, from_id: str, to_id: str, max_depth: int = 10) -> Optional[List[str]]:
        """BFS shortest path from_id -> to_id. None if unreachable / over depth."""

    @abstractmethod
    def cluster_by_tag(self) -> Dict[str, List[str]]:
        """Group node ids by each of their tags (one-to-many, O(n))."""

    @abstractmethod
    def stats(self) -> Dict[str, object]:
        """Compute {total_nodes, total_edges, avg_degree, orphan_count} live."""

    @abstractmethod
    def query_with_abstention(
        self,
        query: str,
        top_k: int = 10,
        semantic_threshold: Optional[float] = None,
    ) -> "tuple[List[Tuple[str, float]], bool]":
        """Semantic/hybrid retrieval WITH confidence-gated abstention (ADR-0XX).

        Returns ``(results, abstained)`` where ``results`` is a best-first list of
        ``(node_id, cosine_score)`` tuples filtered to those at or above
        ``semantic_threshold`` (cosine, 0..1), and ``abstained`` is ``True`` iff no
        candidate cleared the threshold (the engine REFUSES to answer rather than
        return a low-confidence / hallucinated node).

        Zero regression: with no wired semantic_index+embedding, or with
        ``semantic_threshold is None``, returns ``([], True)`` (no vector signal
        available -> cannot assert a match). Callers that do not want abstention
        keep using ``search()`` / ``hybrid_search()`` unchanged.
        """
