"""contracts/cost.py — pure cost estimation port (Phase C.1).

Heuristic pre-call cost (ADR-009 §10) expressed as a CONTRACT-level function so
that neither adapters nor policies depend on each other for it.

    cost = prompt_tokens / 4 * price_per_1k ; free models cost 0.
    prompt_tokens approximated as len(prompt) // 4 (4 chars ~= 1 token).

This resolves V3 (adapters/router.py imported policies.budget_policy.estimate_cost
directly). Now both router and BudgetPolicy import estimate_cost from contracts.
"""
from __future__ import annotations

from contracts.i_llm import ModelInfo, ModelQuery


def estimate_cost(query: ModelQuery, model: ModelInfo) -> float:
    """Heuristic pre-call cost estimate (ADR-009 §10).

    Depends only on contracts.i_llm types. Free models or zero price -> 0.0.
    """
    if model.free or model.cost_per_1k == 0.0:
        return 0.0
    prompt = getattr(query, "prompt", "") or ""
    approx_tokens = max(1, len(prompt) // 4)
    return approx_tokens / 1000.0 * model.cost_per_1k
