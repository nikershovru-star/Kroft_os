"""Self-analysis recorder (TZ-AGENT-001 WP-06, ADR-037 §2, K8).

K1-compliant: contracts only + stdlib. Records health checks and architecture
drift as EXPERIMENT nodes / VIOLATES edges in the Knowledge Graph.
"""
from __future__ import annotations

from contracts.knowledge_graph import Edge, EdgeType, Node, NodeType
from contracts.knowledge_graph import IGraphEngine
from contracts.agent_orchestration import DriftRecord, HealthReport


class SelfAnalysisRecorder:
    """Persists self-analysis results into the Knowledge Graph."""

    def __init__(self, graph: IGraphEngine) -> None:
        self._g = graph

    def _ensure_node(self, node_id: str, ntype: NodeType) -> None:
        if self._g.get_node(node_id) is None:
            self._g.add_node(Node(id=node_id, type=ntype, label=node_id))

    def record_health(self, report: HealthReport) -> Node:
        node = Node(
            id=f"EXP-health-{report.timestamp}",
            type=NodeType.EXPERIMENT,
            label="health-check",
            tenant_id="default",
        )
        self._g.add_node(node)
        return node

    def record_drift(self, drift: DriftRecord, target_adr: str) -> Node:
        node = Node(
            id=f"EXP-drift-{drift.file}-{drift.line}",
            type=NodeType.EXPERIMENT,
            label=f"drift:{drift.rule}",
            tenant_id="default",
        )
        self._g.add_node(node)
        self._ensure_node(target_adr, NodeType.ADR)
        self._g.add_edge(Edge(
            source_id=node.id, target_id=target_adr,
            type=EdgeType.VIOLATES,
        ))
        return node
