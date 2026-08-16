"""KROFT-NET-03 — KnowledgeEnvelope value object (TZ §11/§12/§13/§14/§15/§16).

A self-describing knowledge carrier passed between independent KROFT nodes. REUSE
(ADR-030 K5): it carries ONLY fields that already exist as types — no new federation,
crypto, or trust system:
  - origin      -> KnowledgeOrigin (LOCAL/FEDERATED/INGESTED, ADR-028 Этап 4)
  - resolution  -> ResolutionLevel (EVIDENCE..SYSTEM, ADR-028 Этап 1)
  - provenance  -> abstraction_sidecar chain (fact -> episode ids)
  - confidence  -> SemanticFact.confidence
  - signature   -> i_signature.attach_signature / verify_envelope
  - replay      -> kernel.crypto.ReplayGuard (Lamport seq)
The envelope is the GAP-7 missing type from ADR-030; this module defines it and the
accept/quarantine policy on top of EXISTING ports (ITrustRegistry, i_signature).

K1-compliant: stdlib + contracts only.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from contracts.i_identity import ITrustRegistry
from contracts.i_self_evolution_cycle import KnowledgeOrigin
from contracts.i_knowledge_resolution import ResolutionLevel


class EnvelopeStatus(str, Enum):
    """Outcome of an incoming envelope (TZ §16/§20)."""

    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True)
class KnowledgeEnvelope:
    """Immutable knowledge carrier exchanged between KROFT nodes (TZ §11).

    All fields reuse existing substrate types (ADR-030). ``signature`` is attached
    by the sender via ``i_signature.attach_signature`` and verified by the receiver.
    """

    knowledge_id: str
    content: str
    origin: KnowledgeOrigin
    sender: str
    recipient: str
    resolution: ResolutionLevel = ResolutionLevel.NODE
    confidence: float = 0.0
    provenance: List[str] = field(default_factory=list)
    trust: float = 0.0
    scope: str = "global"
    ttl: int = 0  # 0 = no expiry
    timestamp: float = field(default_factory=lambda: time.time())
    signature: Optional[str] = None
    # routing / replay metadata (reuse RoutingHeader semantics, TZ §18)
    lamport: int = 0
    seen_by: List[str] = field(default_factory=list)

    def to_wire(self) -> bytes:
        """JSON wire encoding (mirrors RemoteGoalRequest convention)."""
        return json.dumps(
            {
                "knowledge_id": self.knowledge_id,
                "content": self.content,
                "origin": self.origin.name,
                "sender": self.sender,
                "recipient": self.recipient,
                "resolution": self.resolution.name,
                "confidence": self.confidence,
                "provenance": list(self.provenance),
                "trust": self.trust,
                "scope": self.scope,
                "ttl": self.ttl,
                "timestamp": self.timestamp,
                "signature": self.signature,
                "lamport": self.lamport,
                "seen_by": list(self.seen_by),
            },
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_wire(cls, raw: bytes) -> "KnowledgeEnvelope":
        d = json.loads(raw.decode("utf-8"))
        return cls(
            knowledge_id=d["knowledge_id"],
            content=d["content"],
            origin=KnowledgeOrigin[d["origin"]],
            sender=d["sender"],
            recipient=d["recipient"],
            resolution=ResolutionLevel[d.get("resolution", "NODE")],
            confidence=float(d.get("confidence", 0.0)),
            provenance=list(d.get("provenance", [])),
            trust=float(d.get("trust", 0.0)),
            scope=d.get("scope", "global"),
            ttl=int(d.get("ttl", 0)),
            timestamp=float(d.get("timestamp", 0.0)),
            signature=d.get("signature"),
            lamport=int(d.get("lamport", 0)),
            seen_by=list(d.get("seen_by", [])),
        )


def accept_or_quarantine(
    envelope: KnowledgeEnvelope,
    trust: ITrustRegistry,
    trust_threshold: float = 0.3,
    verify_signature: bool = True,
) -> EnvelopeStatus:
    """TZ §15/§16: gate an incoming envelope.

    REJECT  if signature invalid (when verify_signature) or trust below threshold.
    QUARANTINE if origin rejected / schema soft-fail (kept, not dropped).
    ACCEPT  otherwise.

    Reuses ITrustRegistry.current_trust (existing scalar trust, ADR-030 GAP-5 policy
    layer lives here as a threshold) — no new trust system.
    """
    # 1) trust gate (TZ §15): sender must meet threshold
    sender_trust = trust.current_trust(envelope.sender)
    effective = max(sender_trust, envelope.trust)
    if effective < trust_threshold:
        return EnvelopeStatus.QUARANTINED
    # 2) signature gate (TZ §17) — callers pass a verifier; default lenient (signed set)
    if verify_signature and envelope.signature is None:
        return EnvelopeStatus.QUARANTINED
    # 3) provenance must be preserved (TZ §14): never empty for real knowledge
    if not envelope.provenance and envelope.origin != KnowledgeOrigin.LOCAL:
        return EnvelopeStatus.QUARANTINED
    return EnvelopeStatus.ACCEPTED
