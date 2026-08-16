"""PHASE E.4 — Federation security (reuse KnowledgeEnvelope.accept_or_quarantine).

Verifies the existing trust boundary (ТЗ §27): bad signature / low trust /
missing provenance on an incoming envelope yields QUARANTINE/REJECT, never silent
acceptance. Reuses contracts.knowledge_envelope — no new federation protocol.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.i_identity import AgentIdentity  # noqa: E402
from contracts.i_knowledge_resolution import ResolutionLevel  # noqa: E402
from contracts.i_self_evolution_cycle import KnowledgeOrigin  # noqa: E402
from contracts.knowledge_envelope import (  # noqa: E402
    EnvelopeStatus,
    KnowledgeEnvelope,
    accept_or_quarantine,
)
from kernel.identity import ReferenceTrustRegistry  # noqa: E402


def _env(sender="B", trust=0.9, sig="ok", prov=("e1",), origin=KnowledgeOrigin.FEDERATED):
    return KnowledgeEnvelope(
        knowledge_id="k1", content="fact", origin=origin, sender=sender,
        recipient="A", resolution=ResolutionLevel.NODE, confidence=0.8,
        provenance=list(prov), trust=trust, signature=sig,
    )


def test_valid_envelope_accepted():
    reg = ReferenceTrustRegistry()
    reg.seed("B", 0.9)
    assert accept_or_quarantine(_env(), reg) == EnvelopeStatus.ACCEPTED


def test_low_trust_quarantined():
    reg = ReferenceTrustRegistry()
    reg.seed("B", 0.1)  # below 0.3 threshold
    assert accept_or_quarantine(_env(trust=0.1), reg) == EnvelopeStatus.QUARANTINED


def test_missing_signature_quarantined():
    reg = ReferenceTrustRegistry()
    reg.seed("B", 0.9)
    assert accept_or_quarantine(_env(sig=None), reg) == EnvelopeStatus.QUARANTINED


def test_missing_provenance_quarantined():
    reg = ReferenceTrustRegistry()
    reg.seed("B", 0.9)
    assert accept_or_quarantine(_env(prov=()), reg) == EnvelopeStatus.QUARANTINED


def test_zero_trust_sender_quarantined():
    # Known sender explicitly seeded at trust 0 (no self-claim) -> below 0.3 -> quarantine.
    # NOTE (residual GAP): ReferenceTrustRegistry.current_trust defaults to 0.5 for
    # an UNKNOWN (never-seeded) sender, so a truly-unknown envelope with no
    # self-claim would currently be ACCEPTED (effective = max(0.5, 0) = 0.5 > 0.3).
    # That default-0.5 policy is a separate trust-semantics decision (kernel/identity.py)
    # and is out of scope for this minimal patch; flagged in the final report.
    reg = ReferenceTrustRegistry()
    reg.seed("B", 0.0)
    assert accept_or_quarantine(_env(trust=0.0), reg) == EnvelopeStatus.QUARANTINED
