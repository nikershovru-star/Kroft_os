"""ProviderSelectionPolicy (Wave 5, ADR-009 §4.4; v2 blend in Wave 7, ADR-010).

Replaces the static `_select_model()` if/else in adapters. This is the ONLY
policy that ranks rather than filters. v0.1 scores are heuristic (binary quality,
free=cheap). Wave 7 (ADR-010) adds an OPTIONAL scorecard blend: when an
IScorecard is supplied, measured `accuracy` is mixed into the heuristic. The
system still works with NO scorecard (back-compatible; LAW 5 + LAW 6).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts.i_eval import IScorecard
from contracts.i_llm import ModelInfo, ModelQuery
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision


class ProviderSelectionPolicy(IPolicy):
    """Rank surviving candidates; pick the best per strategy."""

    def __init__(
        self,
        strategy: str = "scored",
        weights: Dict[str, float] = None,
        scorecard: Optional[IScorecard] = None,
        accuracy_weight: float = 0.4,
    ) -> None:
        self.strategy = strategy
        self.weights = weights or {"latency": 0.3, "quality": 0.5, "cost": 0.2}
        # v2 (ADR-010): measured accuracy from Evaluation Platform.
        self._scorecard = scorecard
        self._accuracy_weight = accuracy_weight

    # --- IPolicy contract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "ProviderSelectionPolicy"

    @property
    def priority(self) -> int:
        return 100

    @property
    def can_veto(self) -> bool:
        return False

    # --- scoring ------------------------------------------------------------
    def _measured_accuracy(self, model_id: str) -> float:
        if self._scorecard is None:
            return 0.0
        return self._scorecard.leaderboard(model_id)

    def _score(self, m: ModelInfo, query: ModelQuery) -> float:
        latency_score = 1.0 / (1.0 + max(m.context_window, 1) * 0.0)  # placeholder
        # avg latency unknown pre-call; use context_window as a proxy for maturity
        latency_score = 0.5 if m.context_window >= 32000 else 0.3
        quality_score = 1.0 if (m.reasoning or query.reasoning is False) else 0.7
        if query.reasoning and not m.reasoning:
            quality_score = 0.1
        cost_score = 1.0 if m.free or m.cost_per_1k == 0.0 else 0.5
        ctx_score = 1.0
        if query.context_window > 0:
            ctx_score = min(query.context_window / max(m.context_window, 1), 1.0)
        w = self.weights
        heuristic = (
            w.get("latency", 0.3) * latency_score
            + w.get("quality", 0.5) * quality_score
            + w.get("cost", 0.2) * cost_score
            + 0.0 * ctx_score
        )
        if self._scorecard is None:
            return heuristic
        # v2: blend measured accuracy (explainable, LAW 4). Normalise heuristic to
        # ~[0,1] by dividing by the sum of used weights so the two terms are comparable.
        used_w = w.get("latency", 0.3) + w.get("quality", 0.5) + w.get("cost", 0.2)
        norm_heuristic = heuristic / used_w if used_w else heuristic
        acc = self._measured_accuracy(m.id)
        blended = (1.0 - self._accuracy_weight) * norm_heuristic + self._accuracy_weight * acc
        return blended

    def evaluate(self, context: PolicyContext, catalog: List[ModelInfo]) -> PolicyDecision:
        if not catalog:
            return PolicyDecision(allowed=True, reason="empty catalog, nothing to rank")

        ranked = sorted(catalog, key=lambda m: self._score(m, context.query), reverse=True)

        if self.strategy == "cheapest":
            ranked.sort(key=lambda m: (m.cost_per_1k, 0), reverse=False)
        elif self.strategy == "fastest":
            ranked.sort(key=lambda m: m.context_window, reverse=False)  # proxy
        elif self.strategy == "greedy":
            # first that satisfies: prefer local if query.local, else any
            for m in catalog:
                if context.query.local and not m.local:
                    continue
                ranked = [m] + [x for x in catalog if x.id != m.id]
                break

        acc_note = ""
        if self._scorecard is not None:
            acc_note = f"; acc(top)={self._measured_accuracy(ranked[0].id):.2f}"
        return PolicyDecision(
            allowed=True,
            selected_model=ranked[0],
            fallback_chain=ranked,  # full ranked catalog; engine uses order for ranking + filter
            reason=f"ranked {len(ranked)} models via {self.strategy}{acc_note}",
            audit_log=[
                f"ProviderSelectionPolicy: top={ranked[0].id} strat={self.strategy}"
                + (f" acc={self._measured_accuracy(ranked[0].id):.2f}" if self._scorecard else "")
            ],
            constraints_applied=[self.name],
        )
