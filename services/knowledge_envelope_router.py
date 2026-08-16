"""KROFT-NET-05 — KnowledgeEnvelope wire transfer + multi-hop (TZ §18/§19/§20).

REUSE (K5, no second transport):
  - TcpEventBus (adapters/tcp_event_bus.py) as the carrier (pub/sub over localhost TCP).
  - KnowledgeEnvelope (contracts/knowledge_envelope.py) for the VO + accept/quarantine policy.
  - verify_envelope + ReplayGuard (contracts/i_signature.py) for signature/replay protection.
  - RoutingHeader semantics (ttl / seen_by) for multi-hop A->B->C.

A node runs one KnowledgeEnvelopeRouter bound to its TcpEventBus. On send it signs the
envelope (HMAC via ISignatureProvider) and publishes to topic ``kroft.knowledge``. On
receive it (1) verifies signature+replay, (2) runs accept_or_quarantine trust gate,
(3) if recipient==self and ACCEPTED -> stores in received-store; if recipient!=self and
ttl>0 -> forwards (multi-hop), appending self to seen_by and decrementing ttl (loop-safe).

No new federation / crypto / trust system — all substrate already exists (ADR-030).
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, List, Optional

from adapters.tcp_event_bus import TcpEventBus
from contracts.i_signature import ISignatureProvider, ReplayGuard, attach_signature, verify_envelope
from contracts.knowledge_envelope import (
    EnvelopeStatus,
    KnowledgeEnvelope,
    accept_or_quarantine,
)

TOPIC = "kroft.knowledge"


class KnowledgeEnvelopeRouter:
    """Transfers KnowledgeEnvelopes between nodes over the existing TcpEventBus."""

    def __init__(
        self,
        node_id: str,
        bus: TcpEventBus,
        trust_registry=None,  # ITrustRegistry (for accept_or_quarantine)
        signer: Optional[ISignatureProvider] = None,
        state_root: Optional[str] = None,
        trust_threshold: float = 0.3,
    ) -> None:
        self.node_id = node_id
        self._bus = bus
        self._trust = trust_registry
        self._signer = signer
        self._replay = ReplayGuard()
        self._trust_threshold = trust_threshold
        self._state_root = state_root or os.path.join(".kroft", "nodes", node_id)
        self._recv_dir = os.path.join(self._state_root, "received")
        os.makedirs(self._recv_dir, exist_ok=True)
        self._received: List[KnowledgeEnvelope] = []
        self._on_accept: Optional[Callable[[KnowledgeEnvelope], None]] = None
        self._seq = 0
        bus.subscribe(TOPIC, self._on_message)

    # --- send (TZ §20 MODE B: SHARE) ---
    def send(self, envelope: KnowledgeEnvelope) -> None:
        # Replay key = (sender/origin, lamport). Use the envelope's own lamport so that
        # re-sending the SAME envelope yields the SAME key (replay rejected, TZ §29). If the
        # envelope carries no lamport, assign a stable one from this router's monotonic clock.
        if envelope.lamport:
            lamport = envelope.lamport
        else:
            self._seq += 1
            lamport = self._seq
        d = json.loads(envelope.to_wire().decode("utf-8"))
        d["causal"] = {"lamport": lamport, "node_origin": envelope.sender}
        d["lamport"] = lamport
        if self._signer is not None:
            d = attach_signature(d, self._signer)
        self._bus.publish(TOPIC, d)

    # --- receive ---
    def _on_message(self, event: dict) -> None:
        # loop-safety: never forward an envelope we already saw
        seen = event.get("seen_by", [])
        if self.node_id in seen:
            return
        # signature + replay guard (TZ §17)
        if not verify_envelope(event, self._signer, self._replay):
            return  # drop invalid/replay
        env = KnowledgeEnvelope.from_wire(json.dumps(event).encode("utf-8"))
        recipient = env.recipient
        # multi-hop: not for us and still alive -> forward (TZ §18)
        if recipient != self.node_id:
            if env.ttl > 1:
                fwd = KnowledgeEnvelope(
                    knowledge_id=env.knowledge_id, content=env.content, origin=env.origin,
                    sender=env.sender, recipient=recipient, resolution=env.resolution,
                    confidence=env.confidence, provenance=list(env.provenance),
                    trust=env.trust, scope=env.scope, ttl=env.ttl - 1,
                    timestamp=env.timestamp, signature=env.signature,
                    lamport=env.lamport, seen_by=list(seen) + [self.node_id],
                )
                self._bus.publish(TOPIC, json.loads(fwd.to_wire().decode("utf-8")))
            return
        # addressed to us: trust gate (TZ §15/§16)
        status = accept_or_quarantine(
            env, self._trust, trust_threshold=self._trust_threshold,
            verify_signature=self._signer is not None,
        ) if self._trust is not None else EnvelopeStatus.ACCEPTED
        if status == EnvelopeStatus.ACCEPTED:
            self._received.append(env)
            self._persist(env)
            if self._on_accept:
                self._on_accept(env)

    # --- accessors ---
    def received(self) -> List[KnowledgeEnvelope]:
        return list(self._received)

    def set_on_accept(self, cb: Callable[[KnowledgeEnvelope], None]) -> None:
        self._on_accept = cb

    def _persist(self, env: KnowledgeEnvelope) -> None:
        path = os.path.join(self._recv_dir, f"{env.knowledge_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(env.to_wire().decode("utf-8"))
        except OSError:
            pass
