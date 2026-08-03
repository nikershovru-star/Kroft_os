"""Network Transport port (ТЗ-NW-01 / ADR-044 / RFC-015) — K1-compliant.

Transports COGNITIVE payloads between kernel nodes over the wire: CognitiveEvents
(with Lamport CausalMark) and WorldState facts. This is the federation substrate that
turns in-process SharedContext federation (TZ-015) into REAL network federation.

K6: services/NetworkFederationService uses this PORT; adapters (TcpEventBus) implement
it. Never import concrete adapters here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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
    def disconnect(self) -> None:
        """Leave the overlay."""
        raise NotImplementedError
