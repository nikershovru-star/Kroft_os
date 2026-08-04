"""Network Transport port (ТЗ-NW-01 / ADR-044 / RFC-015) — K1-compliant.

Transports COGNITIVE payloads between kernel nodes over the wire: CognitiveEvents
(with Lamport CausalMark) and WorldState facts. This is the federation substrate that
turns in-process SharedContext federation (TZ-015) into REAL network federation.

K6: services/NetworkFederationService uses this PORT; adapters (TcpEventBus) implement
it. Never import concrete adapters here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import CognitiveEvent, WorldState


class INetworkTransport(ABC):
    """Ships CognitiveEvents + WorldState facts between nodes (wire lamport).

    The transport carries the causal order: CognitiveEvents embed CausalMark
    (node_origin + lamport), and world-fact messages carry the sender's node_id so the
    receiver can run merge_remote (Lamport receive-bump) — never wall-clock time.
    """

    @abstractmethod
    def connect(self, node_id: str, peers: List[str]) -> None:
        """Join the overlay; establish links to peers (localhost TCP / in-process)."""
        raise NotImplementedError

    @abstractmethod
    def send_event(self, event: CognitiveEvent) -> None:
        """Broadcast a CognitiveEvent (carries its CausalMark) to all peers."""
        raise NotImplementedError

    @abstractmethod
    def send_facts(self, facts: List[dict], sender_node_id: str) -> None:
        """Ship WorldState facts (with sender node_id) for causal merge on receiver."""
        raise NotImplementedError

    @abstractmethod
    def on_event(self, handler: Callable[[CognitiveEvent], None]) -> None:
        """Subscribe to inbound CognitiveEvents from peers."""
        raise NotImplementedError

    @abstractmethod
    def on_facts(self, handler: Callable[[List[dict], str], None]) -> None:
        """Subscribe to inbound WorldState facts (facts, sender_node_id)."""
        raise NotImplementedError

    @abstractmethod
    def send_soft_layer(self, items: List[dict], sender_node_id: str) -> None:
        """Ship the EVOLVED SOFT layer (semantic facts + soft policies) for federated
        self-evolution (ТЗ-FSE-01). Each item is a wire-dict produced by
        ``SoftLayerItem.to_wire`` (kind/content/confidence/causal/provenance/origin).

        The transport carries the causal order + origin node_id so the receiver can
        run a causal, provenance-aware merge (ТЗ-FSE-01 confidence-gate + O1: HARD never
        ships on this channel).
        """
        raise NotImplementedError

    @abstractmethod
    def on_soft_layer(self, handler: Callable[[List[dict], str], None]) -> None:
        """Subscribe to inbound SOFT-layer items (items, sender_node_id)."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Leave the overlay."""
        raise NotImplementedError


@dataclass(frozen=True)
class SoftLayerItem:
    """Frozen wire-DTO for one federated SOFT-layer entry (ТЗ-FSE-01, ADR-066).

    NOT a duck-object: every federated adapter MUST emit/accept this exact VO shape.
    ``kind`` is ``'semantic'`` or ``'soft_policy'``. ``origin`` is the node that learned
    it (provenance). ``confidence`` is the aggregated value (Receiver confidence-gate).
    """
    kind: str            # 'semantic' | 'soft_policy'
    content: str         # SemanticFact.content | Policy.body
    confidence: float
    origin: str          # node_id that learned it
    causal: Optional[dict] = None     # serialized CausalMark (node_origin, lamport)
    provenance: Optional[dict] = None  # serialized Provenance
    author_id: Optional[str] = None    # ТЗ-IDT-01: authoring agent/nоде (default = origin)

    def to_wire(self) -> dict:
        d = {
            "kind": self.kind,
            "content": self.content,
            "confidence": self.confidence,
            "origin": self.origin,
            "causal": self.causal,
            "provenance": self.provenance,
        }
        if self.author_id is not None:
            d["author_id"] = self.author_id
        return d

    @classmethod
    def from_wire(cls, d: dict) -> "SoftLayerItem":
        return cls(
            kind=d["kind"], content=d["content"], confidence=float(d["confidence"]),
            origin=d["origin"], causal=d.get("causal"), provenance=d.get("provenance"),
            author_id=d.get("author_id"),
        )
