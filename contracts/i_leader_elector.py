"""Leader elector port — Raft-lite (WP-14, ADR-043).

K1-compliant: stdlib only. ONLY elects a leader among nodes (term-based heartbeat).
Does NOT replicate a log (per RFC-014 decision). Leader coordinates recovery
(reuse WP-10), followers apply CRDT ops locally.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional


class ILeaderElector(ABC):
    """Minimal Raft: leader election only, no log replication."""

    @abstractmethod
    def start(self, node_id: str, peers: List[str]) -> None:
        """Begin election cycle for this node among peers."""

    @abstractmethod
    def stop(self) -> None:
        """Leave the cluster."""

    @abstractmethod
    def is_leader(self) -> bool:
        ...

    @abstractmethod
    def current_leader(self) -> Optional[str]:
        ...

    @abstractmethod
    def term(self) -> int:
        ...

    def on_leader_change(self, cb: Callable[[str], None]) -> None:  # pragma: no cover
        """Register callback fired when leadership changes (for Supervisor failover)."""
        raise NotImplementedError
