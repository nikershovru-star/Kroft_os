"""Distributed EventBus port — drop-in IEventBus over network (WP-14, ADR-043).

K1-compliant: stdlib only. Extends IEventBus. Local publish keeps InMemoryBus
semantics; join() replicates to peers. Partition -> local-only; reconnect replays
missed ops via CRDT merge. Concrete transports (TCP/WebSocket) live in adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class IDistributedEventBus(ABC):
    """IEventBus + cluster membership (drop-in replacement)."""

    # --- IEventBus surface ---
    def subscribe(self, topic: str, handler) -> None:  # pragma: no cover
        raise NotImplementedError

    def publish(self, topic: str, event: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    def publish_sync(self, topic: str, event: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    # --- distributed surface ---
    @abstractmethod
    def join(self, seed_nodes: List[str]) -> None:
        """Connect to cluster seed nodes (start replication)."""

    @abstractmethod
    def leave(self) -> None:
        """Gracefully leave the cluster."""

    @abstractmethod
    def peers(self) -> List[str]:
        """Currently connected peer node ids."""
