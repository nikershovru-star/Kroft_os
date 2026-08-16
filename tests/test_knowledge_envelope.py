"""KROFT-NET-03 — KnowledgeEnvelope wire + accept/quarantine policy (TZ §11/§15/§16).

Unit tests reusing EXISTING substrate: KnowledgeOrigin (ADR-028), ResolutionLevel
(ADR-028), ReferenceTrustRegistry (kernel/identity). No new federation / crypto.

Run: pytest tests/test_knowledge_envelope.py -q
"""

from __future__ import annotations

from contracts.knowledge_envelope import (
    EnvelopeStatus,
    KnowledgeEnvelope,
    accept_or_quarantine,
)
from contracts.i_self_evolution_cycle import KnowledgeOrigin
from contracts.i_knowledge_resolution import ResolutionLevel
from kernel.identity import ReferenceTrustRegistry


def _env(sender="kroft-01", recipient="kroft-02", trust=0.9, signed=True):
    return KnowledgeEnvelope(
        knowledge_id="k1",
        content="X is true",
        origin=KnowledgeOrigin.LOCAL,
        sender=sender,
        recipient=recipient,
        resolution=ResolutionLevel.SYSTEM,
        confidence=0.9,
        provenance=["fact-1", "ep-2"],
        trust=trust,
        signature="sig-abc" if signed else None,
    )


def test_wire_roundtrip_preserves_origin_lod_provenance():
    e = _env()
    raw = e.to_wire()
    e2 = KnowledgeEnvelope.from_wire(raw)
    assert e2.knowledge_id == e.knowledge_id
    assert e2.origin == KnowledgeOrigin.LOCAL
    assert e2.resolution == ResolutionLevel.SYSTEM
    assert e2.provenance == ["fact-1", "ep-2"]
    assert e2.sender == "kroft-01" and e2.recipient == "kroft-02"


def test_accept_when_trust_sufficient():
    reg = ReferenceTrustRegistry()
    reg.seed("kroft-01", 0.9)
    st = accept_or_quarantine(_env(), reg, trust_threshold=0.3)
    assert st == EnvelopeStatus.ACCEPTED


def test_quarantine_when_trust_below_threshold():
    reg = ReferenceTrustRegistry()
    reg.seed("kroft-01", 0.1)  # below 0.3 threshold
    st = accept_or_quarantine(_env(trust=0.1), reg, trust_threshold=0.3)
    assert st == EnvelopeStatus.QUARANTINED


def test_quarantine_when_signature_missing():
    reg = ReferenceTrustRegistry()
    reg.seed("kroft-01", 0.9)
    st = accept_or_quarantine(_env(signed=False), reg, trust_threshold=0.3)
    assert st == EnvelopeStatus.QUARANTINED


def test_quarantine_when_provenance_empty_federated():
    reg = ReferenceTrustRegistry()
    reg.seed("kroft-01", 0.9)
    e = _env()
    object.__setattr__(e, "provenance", [])  # federated but no chain
    e2 = KnowledgeEnvelope(
        knowledge_id=e.knowledge_id, content=e.content, origin=KnowledgeOrigin.FEDERATED,
        sender=e.sender, recipient=e.recipient, resolution=e.resolution,
        confidence=e.confidence, provenance=[], trust=e.trust, signature=e.signature,
    )
    st = accept_or_quarantine(e2, reg, trust_threshold=0.3)
    assert st == EnvelopeStatus.QUARANTINED
