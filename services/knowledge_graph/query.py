"""Query Interface (TZ-KNOW-001 WP-06, ADR-036).
Python API + CLI helpers for graph traversal and impact analysis.
K1-compliant: contracts + stdlib.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from contracts.knowledge_graph import EdgeType, Node, NodeType
from .engine import InMemoryGraphEngine

class QueryInterface:
    def __init__(self, engine: InMemoryGraphEngine) -> None:
        self._engine = engine

    def query(self, node_id: str, edge_type: Optional[str] = None,
              depth: int = 1) -> List[Node]:
        et = EdgeType(edge_type) if edge_type else None
        return self._engine.traverse(node_id, et, depth)

    def impact(self, node_id: str, depth: int = 2) -> Dict[str, List[Node]]:
        return self._engine.impact_analysis(node_id, depth)

    def cycles(self) -> List[List[str]]:
        return self._engine.find_cycles()

    def orphans(self) -> List[Node]:
        """Nodes with no incoming edges (no references)."""
        all_ids = {n.id for n in self._engine.nodes()}
        referenced = {e.target_id for e in self._engine.edges()}
        return [self._engine.get_node(nid) for nid in all_ids - referenced
                if self._engine.get_node(nid)]

    def stats(self) -> Dict[str, Any]:
        return {
            "nodes": len(self._engine.nodes()),
            "edges": len(self._engine.edges()),
            "cycles": len(self._engine.find_cycles()),
            "orphans": len(self.orphans()),
        }

# CLI helpers (thin wrappers, no argparse here — wired in composition/CLI)
def cli_graph_query(engine: InMemoryGraphEngine, node_id: str,
                    edge_type: Optional[str], depth: int) -> str:
    qi = QueryInterface(engine)
    nodes = qi.query(node_id, edge_type, depth)
    lines = [f"{n.id} [{n.type.value}] {n.label}" for n in nodes]
    return "\n".join(lines) if lines else "(no results)"

def cli_graph_impact(engine: InMemoryGraphEngine, node_id: str, depth: int) -> str:
    qi = QueryInterface(engine)
    groups = qi.impact(node_id, depth)
    lines = [f"Impact of {node_id} (depth={depth}):"]
    for k, v in groups.items():
        lines.append(f"  {k}: {len(v)} nodes")
        for n in v:
            lines.append(f"    - {n.id}: {n.label}")
    return "\n".join(lines)

def cli_graph_cycles(engine: InMemoryGraphEngine) -> str:
    cycles = engine.find_cycles()
    if not cycles:
        return "No cycles detected."
    lines = [f"Cycle {i+1}: {' -> '.join(c)}" for i, c in enumerate(cycles)]
    return "\n".join(lines)
