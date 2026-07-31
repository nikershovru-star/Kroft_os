"""(services) SimpleGuardrail — IGuardrail (Wave 13, ADR-016 Phase D).

v0.1 risk model: `risk_score = 1.0 - rec.confidence` (the more confident the
source pattern, the lower the risk). Classifies the stage but NEVER applies
anything — the guardrail is read-only classification (Roadmap guardrail:
Recommendation → Shadow → Canary → Approval → Rollback).

LAW 2: imports only contracts.*.
LAW 4/LAW 5: the decision is explainable and derived from the measured
confidence, not a guess.
"""
from __future__ import annotations

from typing import List

from contracts.i_learning import ExecutionTrace
from contracts.i_optimization import (
    GUARD_APPROVED,
    GUARD_CANARY,
    GUARD_SHADOW,
    IGuardrail,
    GuardrailResult,
    Recommendation,
)


class SimpleGuardrail(IGuardrail):
    """Classify a recommendation's risk from its confidence (v0.1)."""

    # thresholds on risk_score (1.0 - confidence)
    APPROVED_MAX = 0.2   # risk < 0.2  -> approved
    CANARY_MAX = 0.5     # 0.2..0.5    -> canary
    # >= 0.5            -> shadow

    def validate(
        self, rec: Recommendation, traces: List[ExecutionTrace]
    ) -> GuardrailResult:
        # v0.1: risk from confidence only. `traces` is accepted for v1.0
        # (future: history-aware scoring) but unused here.
        risk = max(0.0, min(1.0, 1.0 - rec.confidence))

        if risk < self.APPROVED_MAX:
            stage = GUARD_APPROVED
            allowed = True
        elif risk < self.CANARY_MAX:
            stage = GUARD_CANARY
            allowed = True  # canary is shippable to a subset, not auto-applied
        else:
            stage = GUARD_SHADOW
            allowed = False

        explanation = (
            f"risk_score={risk:.2f} from confidence={rec.confidence:.2f}. "
            f"Stage={stage}. "
            + ("Auto-apply permitted after approval." if allowed
               else "Observe only — requires stronger evidence before canary.")
        )
        return GuardrailResult(
            allowed=allowed,
            stage=stage,
            risk_score=risk,
            explanation=explanation,
        )
