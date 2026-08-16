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

from contracts.i_event_bus import IEventBus
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
        bus: IEventBus,
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
        # TZ §16: quarantined/rejected envelopes must NOT silently vanish — they land here.
        self._quar_dir = os.path.join(self._state_root, "quarantine")
        os.makedirs(self._quar_dir, exist_ok=True)
        self._quarantined: List[tuple] = []  # (EnvelopeStatus, KnowledgeEnvelope, reason)
        self._on_quarantine: Optional[Callable[[EnvelopeStatus, KnowledgeEnvelope, str], None]] = None
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
        # signature + replay guard (TZ §17). TZ §16: do NOT silently drop — quarantine it.
        if not verify_envelope(event, self._signer, self._replay):
            env = KnowledgeEnvelope.from_wire(json.dumps(event).encode("utf-8"))
            self._quarantine(EnvelopeStatus.REJECTED, env, "signature_invalid_or_replay")
            return
        env = KnowledgeEnvelope.from_wire(json.dumps(event).encode("utf-8"))
        recipient = env.recipient
        # multi-hop: not for us and still alive -> forward (TZ §18)
        # Forward the ORIGINAL event dict (keeps causal/lamport/signature/_canonical_version
        # intact) — do NOT re-serialize via KnowledgeEnvelope.to_wire() (would drop them)!
        # Do NOT forward an envelope WE ourselves originated (sender == self) — only relay
        # envelopes that arrived from another node (prevents self-loop echo).
        if recipient != self.node_id and env.sender != self.node_id:
            if env.ttl > 1:
                fwd = dict(event)
                fwd["ttl"] = env.ttl - 1
                fwd["seen_by"] = list(seen) + [self.node_id]
                self._bus.publish(TOPIC, fwd)
            return
        # addressed to us: trust gate (TZ §15/§16)
        status = accept_or_quarantine(
            env, self._trust, trust_threshold=self._trust_threshold,
            verify_signature=self._signer is not None,
        )
        if status == EnvelopeStatus.ACCEPTED:
            self._received.append(env)
            self._persist(env)
            if self._on_accept:
                self._on_accept(env)
        elif status in (EnvelopeStatus.QUARANTINED, EnvelopeStatus.REJECTED):
            # TZ §16: keep it, do not silently drop
            self._quarantine(status, env, "trust_gate")

    def _quarantine(self, status: EnvelopeStatus, env: KnowledgeEnvelope, reason: str) -> None:
        self._quarantined.append((status, env, reason))
        path = os.path.join(self._quar_dir, f"{env.knowledge_id}.{status.name}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(env.to_wire().decode("utf-8"))
        except OSError:
            pass
        if self._on_quarantine:
            self._on_quarantine(status, env, reason)

    # --- accessors ---
    def received(self) -> List[KnowledgeEnvelope]:
        return list(self._received)

    def quarantined(self) -> List[tuple]:
        """TZ §16/§28: envelopes that were rejected/quarantined (not silently dropped)."""
        return list(self._quarantined)

    def set_on_accept(self, cb: Callable[[KnowledgeEnvelope], None]) -> None:
        self._on_accept = cb

    def set_on_quarantine(self, cb: Callable[[EnvelopeStatus, KnowledgeEnvelope, str], None]) -> None:
        self._on_quarantine = cb

    def _persist(self, env: KnowledgeEnvelope) -> None:
        path = os.path.join(self._recv_dir, f"{env.knowledge_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(env.to_wire().decode("utf-8"))
        except OSError:
            pass
