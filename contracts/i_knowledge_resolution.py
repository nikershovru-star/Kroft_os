"""Knowledge Resolution port (Multi-Resolution / LOD, ADR-028).

K1-compliant: stdlib + contracts ONLY. No service/adapter/runtime imports.

Gives ONE KROFT_OS instance the ability to present its knowledge at the
right level of abstraction while keeping the evidence chain intact down to
the original observations. This is the vocabulary the other ADR-028 stages
(2: sidecar, 3: cosmic perspective, 4: ownership boundary) are expressed in.

The port never invents new graph traversal: it delegates to IGraphQuery /
IGraphBuilder (get_cluster, top_central, shortest_path, compound_query,
cluster_by_tag, backlinks) which already exist. Clustering is a STABLE rule
(no LLM in the kernel) so resolution is deterministic (I-09).

Invariant: `provenance` is NEVER empty. An item with no source is an error,
not a degraded view — this is the proof-over-existence guarantee.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Protocol


class ResolutionLevel(IntEnum):
    """Coarse-to-fine abstraction ladder. Lower = more detail."""

    EVIDENCE = 0   # raw observations / document fragments
    NODE = 1       # graph nodes as-is
    CONCEPT = 2    # a cluster of nodes collapsed into one concept
    SUBSYSTEM = 3  # a cluster of concepts
    SYSTEM = 4     # one summary of the whole area


@dataclass(frozen=True)
class ResolvedItem:
    """One visible element at a given resolution level."""

    id: str
    label: str
    level: ResolutionLevel
    collapsed_from: int = 0          # how many lower-level items it summarizes
    provenance: List[str] = field(default_factory=list)  # source ids, never empty


@dataclass(frozen=True)
class ResolvedView:
    """A snapshot of knowledge at one resolution level for a query."""

    level: ResolutionLevel
    query: str
    items: List[ResolvedItem]
    collapsed_from: int = 0          # total nodes folded into this view
    provenance: List[str] = field(default_factory=list)  # union of item provenance


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer to a source observation/fragment at the bottom of the chain."""

    id: str
    kind: str = "observation"        # observation | fragment | node
    label: str = ""


class IKnowledgeResolution(Protocol):
    """Port for multi-resolution knowledge views over a knowledge graph."""

    @abstractmethod
    def view(self, query: str, level: ResolutionLevel) -> ResolvedView:
        """Return the knowledge matching `query` at `level`."""

    @abstractmethod
    def zoom_out(self, view: ResolvedView) -> ResolvedView:
        """Coarsen one level (NODE->CONCEPT->SUBSYSTEM->SYSTEM)."""

    @abstractmethod
    def zoom_in(self, item_id: str) -> ResolvedView:
        """Refine one item to the next-finer level (SYSTEM->SUBSYSTEM->...->NODE)."""

    @abstractmethod
    def evidence_for(self, item_id: str) -> List[EvidenceRef]:
        """Walk the provenance chain down to EVIDENCE. Must never return empty
        for a real item — emptiness is an error, not degradation."""
