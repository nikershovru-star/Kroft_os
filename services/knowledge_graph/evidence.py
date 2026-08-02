"""Evidence Traceability (TZ-KNOW-001 WP-05, ADR-036).
Links tests/experiments to ADR nodes. F6 mitigation: detect ADRs without evidence.
K1-compliant: contracts + stdlib.
"""
from __future__ import annotations
from typing import List, Optional
from contracts.knowledge_graph import Edge, EdgeType, Node, NodeType
from .engine import InMemoryGraphEngine

class EvidenceLinker:
    def __init__(self, engine: InMemoryGraphEngine) -> None:
        self._engine = engine

    def link_test_to_adr(self, test_name: str, adr_id: str,
                         evidence_type: str = "test") -> None:
        nid = f"TEST:{test_name}"
        if self._engine.get_node(nid) is None:
            self._engine.add_node(Node(id=nid, type=NodeType.EXPERIMENT,
                                       label=test_name,
                                       metadata={"evidence_type": evidence_type}))
        if self._engine.get_node(adr_id):
            self._engine.add_edge(Edge(source_id=nid, target_id=adr_id, type=EdgeType.VALIDATES))

    def link_experiment_to_adr(self, exp_id: str, adr_id: str) -> None:
        if self._engine.get_node(exp_id) is None:
            self._engine.add_node(Node(id=exp_id, type=NodeType.EXPERIMENT,
                                       label=exp_id))
        if self._engine.get_node(adr_id):
            self._engine.add_edge(Edge(source_id=exp_id, target_id=adr_id, type=EdgeType.PROVES))

    def get_evidence_for(self, adr_id: str) -> List[Node]:
        result: List[Node] = []
        for e in self._engine.edges():
            if e.target_id == adr_id and e.type in (EdgeType.VALIDATES, EdgeType.PROVES):
                n = self._engine.get_node(e.source_id)
                if n:
                    result.append(n)
        return result

    def get_adrs_without_evidence(self) -> List[Node]:
        adrs = [n for n in self._engine.nodes() if n.type == NodeType.ADR]
        proven = {e.target_id for e in self._engine.edges()
                  if e.type in (EdgeType.VALIDATES, EdgeType.PROVES)}
        return [n for n in adrs if n.id not in proven]
