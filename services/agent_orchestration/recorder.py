"""Agent run recorder (TZ-AGENT-001 WP-06, ADR-037 §2, K8).

K1-compliant: contracts only + stdlib. Records agent runs as EXPERIMENT nodes
in the Knowledge Graph, linked to ADRs via PROVES/VIOLATES edges. Reuses the
graph engine port + EvidenceLinker-style edge semantics from TZ-KNOW-001.
"""
from __future__ import annotations

from contracts.knowledge_graph import Edge, EdgeType, Node, NodeType
from contracts.knowledge_graph import IGraphEngine


class AgentRunRecorder:
    """Persists agent-run outcomes into the Knowledge Graph."""

    def __init__(self, graph: IGraphEngine) -> None:
        self._g = graph

    def _ensure_node(self, node_id: str, ntype: NodeType) -> None:
        if self._g.get_node(node_id) is None:
            self._g.add_node(Node(id=node_id, type=ntype, label=node_id))

    def record_run(
        self,
        goal_id: str,
        tenant_id: str,
        proves_adr: str | None = None,
        violates_adr: str | None = None,
    ) -> Node:
        node = Node(
            id=f"EXP-{goal_id}",
            type=NodeType.EXPERIMENT,
            label=goal_id,
            tenant_id=tenant_id,
        )
        self._g.add_node(node)
        if proves_adr:
            self._ensure_node(proves_adr, NodeType.ADR)
            self._g.add_edge(Edge(
                source_id=node.id, target_id=proves_adr,
                type=EdgeType.PROVES,
            ))
        if violates_adr:
            self._ensure_node(violates_adr, NodeType.ADR)
            self._g.add_edge(Edge(
                source_id=node.id, target_id=violates_adr,
                type=EdgeType.VIOLATES,
            ))
        return node
