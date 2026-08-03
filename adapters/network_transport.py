"""Network transport adapter — ТЗ-NW-01 (ADR-044 / RFC-015). K8-compliant: adapters/.

Implements INetworkTransport by wrapping the WP-14 TcpEventBus (localhost TCP) and
mapping COGNITIVE payloads (CognitiveEvent, WorldState facts) to wire dicts. Wire key
is `lamport` (ТЗ-RE-01); causal order travels via CausalMark, never wall-clock time.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import CognitiveEvent
from contracts.i_network_transport import INetworkTransport
from adapters.tcp_event_bus import TcpEventBus


class NetworkTransport(INetworkTransport):
    """TCP-backed INetworkTransport. Ships CognitiveEvents + world facts to peers.

    Uses two topics: ``cog.event`` (CognitiveEvent payload) and ``cog.facts``
    (WorldState facts + sender node_id). On receive, handlers are invoked so the
    federation service can run causal merge (merge_remote / Lamport receive-bump).

    Federation-robust: ``connect`` spawns a background retry thread (NOT wall-clock
    sleep) that keeps (re)establishing peer links until the desired peer count is
    reached or the node leaves — so both directions come up reliably without timing
    luck (ТЗ-NW-01 determinism principle).
    """

    def __init__(self, node_id: str, port: int, host: str = "127.0.0.1") -> None:
        self._bus = TcpEventBus(node_id, port, host)
        self._ev_handlers: List[Callable[[CognitiveEvent], None]] = []
        self._fact_handlers: List[Callable[[List[dict], str], None]] = []
        self._seeds: List[str] = []
        self._expected_peers = 0
        self._stop = threading.Event()
        self._connector: Optional[threading.Thread] = None
        self._connect_timeout: float = 1.0  # SOFT tunable (runtime reflection, O1)
        self._bus.subscribe("cog.event", self._on_wire_event)
        self._bus.subscribe("cog.facts", self._on_wire_facts)

    # --- INetworkTransport ---
    def connect(self, node_id: str, peers: List[str]) -> None:
        self._seeds = list(peers)
        self._expected_peers = len(peers)
        self._bus.join(peers)  # initial attempt (starts server + first connects)
        # background retry until bidirectional links are up (no sleep-based luck)
        self._stop.clear()
        self._connector = threading.Thread(target=self._connect_loop, daemon=True)
        self._connector.start()

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            if len(self._bus.peers()) >= self._expected_peers:
                break  # all peers linked bidirectionally
            try:
                self._bus.join(self._seeds)
            except OSError:
                pass
            self._stop.wait(0.2)

    def ensure_connected(self, timeout: Optional[float] = None) -> bool:
        """Deterministic barrier: block until the expected peers are linked.

        Uses `timeout` if given, else the SOFT-tunable `self._connect_timeout`
        (runtime reflection may raise it under poor delivery, O1-guarded).
        """
        if timeout is None:
            timeout = self._connect_timeout
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self._bus.peers()) >= self._expected_peers:
                return True
            self._stop.wait(0.1)
        return len(self._bus.peers()) >= self._expected_peers

    def send_event(self, event: CognitiveEvent) -> None:
        self._bus.publish_sync("cog.event", event.to_bus())

    def send_facts(self, facts: List[dict], sender_node_id: str) -> None:
        self._bus.publish_sync("cog.facts", {"facts": facts, "sender": sender_node_id})

    def on_event(self, handler: Callable[[CognitiveEvent], None]) -> None:
        self._ev_handlers.append(handler)

    def on_facts(self, handler: Callable[[List[dict], str], None]) -> None:
        self._fact_handlers.append(handler)

    def disconnect(self) -> None:
        self._stop.set()
        self._bus.leave()

    # --- wire mapping ---
    def _on_wire_event(self, payload: dict) -> None:
        ev = CognitiveEvent.from_bus(payload)
        for h in self._ev_handlers:
            h(ev)

    def _on_wire_facts(self, payload: dict) -> None:
        facts = payload.get("facts", [])
        sender = payload.get("sender", "")
        for h in self._fact_handlers:
            h(facts, sender)
