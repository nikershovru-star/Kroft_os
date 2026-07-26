"""Graph builder port (Hexagonal Architecture).

A service-style port: it expresses an application capability (building a
knowledge graph) and therefore inherits IService. Concrete implementations
(e.g. InMemoryGraphBuilder) are injected via the DI container.
"""
from __future__ import annotations
from abc import abstractmethod
from typing import Any, Dict, List

from .i_service import IService


class IGraphBuilder(IService):
    """Port for constructing an in-memory knowledge graph."""

    @abstractmethod
    def add_node(self, id: str, label: str, meta: dict) -> None: ...

    @abstractmethod
    def add_edge(self, from_id: str, to_id: str, relation: str) -> None: ...

    @abstractmethod
    def get_graph(self) -> dict:
        """Return a snapshot: {"nodes": [...], "edges": [...]}."""

    @abstractmethod
    def get_neighbors(self, node_id: str) -> List[str]:
        """Return ids of nodes directly reachable from node_id."""

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def snapshot(self, fs: "IFileSystem", path: str) -> None:
        """Persist current graph to JSON at `path` via the IFileSystem port."""

    @abstractmethod
    def restore(self, fs: "IFileSystem", path: str) -> bool:
        """Load graph from JSON at `path` via IFileSystem.

        Returns True on successful load, False if the file is missing or
        corrupt (in which case the graph is left empty and no exception leaks).
        """
