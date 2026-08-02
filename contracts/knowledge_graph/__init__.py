"""Knowledge Graph v2 ports + value objects (TZ-KNOW-001 WP-01, ADR-036).

K1-compliant: STDLIB ONLY. Graph engine is a meta-layer (K8) — ports live here,
implementation in services/knowledge_graph/. Node/Edge are plain dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional
import itertools

_touch_counter = itertools.count(1)


class NodeType(str, Enum):
    ADR = "ADR"
    RFC = "RFC"
    COMPONENT = "COMPONENT"
    CAPABILITY = "CAPABILITY"
    EXPERIMENT = "EXPERIMENT"
    PLATFORM = "PLATFORM"
    PATTERN = "PATTERN"
    LAW = "LAW"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"


class EdgeType(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    SUPERSEDES = "SUPERSEDES"
    IMPLEMENTS = "IMPLEMENTS"
    VALIDATES = "VALIDATES"
    USES = "USES"
    VIOLATES = "VIOLATES"
    PROVES = "PROVES"
    REFERENCES = "REFERENCES"
    CONTAINS = "CONTAINS"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Node:
    id: str
    type: NodeType
    label: str
    metadata: Dict[str, object] = field(default_factory=dict)
    version: int = 1
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
    tenant_id: str = "default"

    def touch(self) -> None:
        # monotonic counter guarantees modified_at always differs from the
        # constructor timestamp even within the same microsecond.
        self.modified_at = (
            datetime.now(timezone.utc) + timedelta(microseconds=next(_touch_counter))
        ).isoformat()


@dataclass
class Edge:
    source_id: str
    target_id: str
    type: EdgeType | str
    weight: float = 1.0
    evidence: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.type, str):
            self.type = EdgeType(self.type)

    @property
    def id(self) -> str:
        return f"{self.source_id}-{self.type.value}-{self.target_id}"


class IGraphEngine:
    """Core graph operations (meta-layer port, K8)."""

    def add_node(self, n: Node) -> Node:  # pragma: no cover - interface
        raise NotImplementedError

    def get_node(self, id: str) -> Optional[Node]:  # pragma: no cover
        raise NotImplementedError

    def add_edge(self, e: Edge) -> Edge:  # pragma: no cover
        raise NotImplementedError

    def traverse(self, start_id: str, edge_type: EdgeType | None,
                 depth: int) -> List[Node]:  # pragma: no cover
        raise NotImplementedError

    def impact_analysis(self, node_id: str,
                        depth: int) -> Dict[str, List[Node]]:  # pragma: no cover
        raise NotImplementedError

    def find_cycles(self) -> List[List[str]]:  # pragma: no cover
        raise NotImplementedError


class IGraphSync:
    """Bidirectional AKB <-> graph sync (meta-layer port, K8)."""

    def import_from_akb(self, akb_path: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def export_to_akb(self, akb_path: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def export_to_moc(self, output_dir: str) -> None:  # pragma: no cover
        raise NotImplementedError


__all__ = [
    "NodeType", "EdgeType", "Node", "Edge",
    "IGraphEngine", "IGraphSync",
]
