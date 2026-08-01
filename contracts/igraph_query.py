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
from typing import Dict, List, Optional

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
