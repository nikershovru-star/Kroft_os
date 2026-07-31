"""ProviderSelectionPolicy (Wave 5, ADR-009 §4.4).

Replaces the static `_select_model()` if/else in adapters. This is the ONLY
policy that ranks rather than filters. v0.1 scores are heuristic (binary quality,
free=cheap); v1.0 plugs in eval-datasets.
"""
from __future__ import annotations

from typing import Dict, List

from contracts.i_llm import ModelInfo, ModelQuery
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision


class ProviderSelectionPolicy(IPolicy):
    """Rank surviving candidates; pick the best per strategy."""

    def __init__(self, strategy: str = "scored", weights: Dict[str, float] = None) -> None:
        self.strategy = strategy
        self.weights = weights or {"latency": 0.3, "quality": 0.5, "cost": 0.2}

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
        return (
            w.get("latency", 0.3) * latency_score
            + w.get("quality", 0.5) * quality_score
            + w.get("cost", 0.2) * cost_score
            + 0.0 * ctx_score
        )

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

        return PolicyDecision(
            allowed=True,
            selected_model=ranked[0],
            fallback_chain=ranked,  # full ranked catalog; engine uses order for ranking + filter
            reason=f"ranked {len(ranked)} models via {self.strategy}",
            audit_log=[f"ProviderSelectionPolicy: top={ranked[0].id} strat={self.strategy}"],
            constraints_applied=[self.name],
        )
