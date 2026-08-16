"""Hypothesis Engine — deterministic translation of gaps/evidence into evolution
hypotheses (Self-Evolution Wave, STEP 7).

K1-compliant: stdlib + contracts only. No service/adapter/runtime imports.
LLM-free reference implementation: hypotheses are rule-generated from structured
inputs (CapabilityGap + evidence), not free-form text.

REUSE: EvolutionHypothesis, CapabilityGap, CausalEvent already live in
contracts/i_self_evolution_cycle.py.
"""

from __future__ import annotations

from typing import List, Optional

from contracts.i_self_evolution_cycle import (
    CapabilityGap,
    CausalEvent,
    EvolutionHypothesis,
    IHypothesisEngine,
)


class ReferenceHypothesisEngine(IHypothesisEngine):
    """Deterministic hypothesis generator from capability gaps + causal evidence.

    For each gap it produces at most one hypothesis with:
      - problem            : gap summary
      - evidence           : grounded in causal outcomes or explicit evidence text
      - suspected_cause    : direct mapping from gap.evidence or causal change
      - proposed_change    : deterministic action template
      - expected_effect    : gap improvement direction
      - metric             : gap metric
      - acceptance_threshold : conservative default = 10% of gap closure
    """

    _DEFAULT_THRESHOLD_RATIO = 0.10

    def __init__(self, threshold_ratio: float = _DEFAULT_THRESHOLD_RATIO) -> None:
        self.threshold_ratio = max(0.0, min(1.0, float(threshold_ratio)))

    def formulate(
        self,
        gap: CapabilityGap,
        evidence: str = "",
        suspected_cause: str = "",
    ) -> Optional[EvolutionHypothesis]:
        if not gap or gap.gap <= 0.0:
            return None

        threshold = max(0.0, gap.gap * self.threshold_ratio)
        return EvolutionHypothesis(
            id=self._id_for(gap),
            problem=f"{gap.name} capability gap: {gap.status} ({gap.score:.3f} vs target {gap.target:.3f})",
            evidence=evidence or gap.evidence or "no explicit evidence",
            suspected_cause=suspected_cause or gap.evidence or "unknown",
            proposed_change=self._proposed_change_for(gap),
            expected_effect=f"close {gap.gap:.3f} gap on {gap.name}",
            metric=gap.metric if gap.metric else gap.name,
            acceptance_threshold=_round_threshold(threshold),
        )

    def formulate_from_causal(
        self,
        gap: CapabilityGap,
        causal: CausalEvent,
    ) -> Optional[EvolutionHypothesis]:
        return self.formulate(
            gap=gap,
            evidence=causal.observation or causal.outcome,
            suspected_cause=causal.change or causal.action,
        )

    @staticmethod
    def _id_for(gap: CapabilityGap) -> str:
        return f"hyp-{gap.name}-{abs(hash((gap.name, gap.status, gap.evidence)) % 100000):05d}"

    @staticmethod
    def _proposed_change_for(gap: CapabilityGap) -> str:
        status = gap.status.lower()
        if status == "missing":
            return f"add core capability for {gap.name}"
        if status == "degraded":
            return f"repair existing {gap.name} capability"
        if status == "bad":
            return f"replace current {gap.name} implementation"
        return f"optimize {gap.name} behavior"


def _round_threshold(value: float) -> float:
    return round(value, 6)
