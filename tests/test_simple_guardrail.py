"""services/test_simple_guardrail.py — risk score -> stage (Wave 13).

Verifies the guardrail CLASSIFIES only (no apply) and maps risk correctly.
"""
from __future__ import annotations

from contracts.i_learning import ExecutionTrace, Pattern
from contracts.i_optimization import (
    GUARD_APPROVED,
    GUARD_CANARY,
    GUARD_SHADOW,
    Recommendation,
)
from services.simple_guardrail import SimpleGuardrail


def _rec(confidence, source="phi4 better"):
    return Recommendation(
        id="r", target="policy:x:w", value="{}", rationale="r",
        confidence=confidence, source_pattern=source,
    )


def test_high_confidence_approved() -> None:
    g = SimpleGuardrail().validate(_rec(0.95), [])
    assert g.stage == GUARD_APPROVED
    assert g.allowed is True
    assert g.risk_score == 0.05


def test_mid_confidence_canary() -> None:
    g = SimpleGuardrail().validate(_rec(0.65), [])
    assert g.stage == GUARD_CANARY
    assert g.allowed is True  # canary shippable to subset, not auto-applied
    assert abs(g.risk_score - 0.35) < 1e-9


def test_low_confidence_shadow() -> None:
    g = SimpleGuardrail().validate(_rec(0.3), [])
    assert g.stage == GUARD_SHADOW
    assert g.allowed is False


def test_guardrail_does_not_mutate_rec() -> None:
    rec = _rec(0.9)
    SimpleGuardrail().validate(rec, [])
    assert rec.status == "proposed"  # unchanged


def test_explanation_present() -> None:
    g = SimpleGuardrail().validate(_rec(0.8), [])
    assert "risk_score" in g.explanation and "Stage" in g.explanation
