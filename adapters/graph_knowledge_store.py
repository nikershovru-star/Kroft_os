"""GraphKnowledgeStore — IKnowledgeGraph over the existing graph engine
(Wave 8, ADR-011 Phase D integration).

ADR-011 §2: "Не переписывай Graph-движок целиком — интегрируй существующий
(InMemoryGraphBuilder, GraphQueryEngine) через адаптер."

The builder is INJECTED (structurally typed: anything with add_node/add_edge/
get_graph), so this adapter imports `contracts` only and never
`infrastructure.graph_builder` — the dependency axis stays adapters -> contracts.

Fact provenance mapping (Definition of Done, ADR-011 §2.5):
  edge  {from: subject, to: object, relation: predicate}
  node  meta = {source, evidence, confidence, history}
The Fact objects themselves are kept verbatim in this adapter so nothing is
lost in the lossy dict form of the underlying graph.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

from contracts.i_knowledge import Fact, IKnowledgeGraph


class _GraphBuilderLike(Protocol):
    """Structural port: the subset of IGraphBuilder this adapter needs."""

    def add_node(self, id: str, label: str, meta: dict) -> None: ...
    def add_edge(self, from_id: str, to_id: str, relation: str) -> None: ...
    def get_graph(self) -> dict: ...


class GraphKnowledgeStore(IKnowledgeGraph):
    """Writes VERIFIED Facts into an existing graph builder."""

    def __init__(self, builder: _GraphBuilderLike) -> None:
        self._builder = builder
        # authoritative Fact store (the graph dict form is lossy)
        self._facts: Dict[Tuple[str, str, str], Fact] = {}

    # --- IKnowledgeGraph ---------------------------------------------------
    def add_fact(self, fact: Fact) -> bool:
        key = fact.key()
        if key in self._facts:
            return False

        meta: Dict[str, Any] = {
            "source": fact.source,
            "evidence": fact.evidence,
            "confidence": fact.confidence,
            "history": [dict(h) for h in fact.history],
            "kind": "fact",
        }
        self._builder.add_node(fact.subject, fact.subject, dict(meta))
        self._builder.add_node(fact.object, fact.object, dict(meta))
        self._builder.add_edge(fact.subject, fact.object, fact.predicate)
        self._facts[key] = fact
        return True

    def facts(self) -> List[Fact]:
        return list(self._facts.values())

    def find(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
    ) -> List[Fact]:
        return [
            f
            for f in self._facts.values()
            if (subject is None or f.subject == subject)
            and (predicate is None or f.predicate == predicate)
            and (object is None or f.object == object)
        ]

    # --- convenience -------------------------------------------------------
    def graph_snapshot(self) -> dict:
        """Underlying graph in its native dict form (nodes/edges)."""
        return self._builder.get_graph()
