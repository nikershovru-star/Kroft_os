"""Graph-backed implementation of IAgentMemoryHandoff (ADR-033).

Persistent agent-to-agent handoff over the EXISTING Knowledge Graph — no
external MCP server. Reuses the Multi-Resolution query API (nodes_by_metadata)
implemented earlier this session; adds NO new query methods.

K1/K6-compliant: imports ONLY contracts (agent_orchestration, igraph_builder,
igraph_query). No kernel / services / adapters / infrastructure imports.
The concrete graph engine (InMemoryGraphBuilder / CrdtGraphEngine) is injected
via DependencyContainer in composition/ (dependency inversion, K3).
"""
from __future__ import annotations

from typing import Dict, List

from contracts.agent_orchestration import (
    AgentDivision,
    AgentMemoryHandoff,
    IAgentMemoryHandoff,
)
from contracts.igraph_builder import IGraphBuilder
from contracts.igraph_query import IGraphQuery

_HANDOFF_TYPE = "handoff"  # workflow artifact, NOT a trusted knowledge FACT


class GraphBackedHandoff(IAgentMemoryHandoff):
    """Stores agent deliverables as graph nodes; reads them back by division."""

    def __init__(self, builder: IGraphBuilder, query: IGraphQuery) -> None:
        self._builder = builder
        self._query = query

    def publish_handoff(self, ho: AgentMemoryHandoff, payload: dict) -> str:
        node_id = (
            f"handoff:{ho.workflow_id}:{ho.step_id}:{ho.consumer_division.value}"
        )
        meta: Dict[str, object] = {
            "type": _HANDOFF_TYPE,
            "level": "handoff",
            "workflow_id": ho.workflow_id,
            "step_id": ho.step_id,
            "division": ho.consumer_division.value,
            "producer_agent_id": ho.producer_agent_id,
            "payload": payload,
        }
        self._builder.add_node(node_id, f"handoff:{ho.step_id}", meta)
        return node_id

    def consume_handoff(
        self, workflow_id: str, consumer_division: AgentDivision
    ) -> List[dict]:
        ids = set(self._query.nodes_by_metadata("workflow_id", workflow_id))
        if not ids:
            return []
        out: List[dict] = []
        for n in self._builder.get_graph()["nodes"]:
            meta = n.get("meta", {})
            if n["id"] in ids and meta.get("division") == consumer_division.value:
                out.append(meta.get("payload"))
        return out
