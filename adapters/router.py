"""Router — integration of PolicyEngine + ILlm (Wave 5, ADR-009 §7.2).

Replaces the static `_select_model()` routing inside adapters. Router asks the
PolicyEngine for a decision, picks the adapter by the chosen model's provider,
and delegates execution (with fallback) to the engine.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext
from policies.budget_policy import estimate_cost
from services.policy_engine import PolicyEngine


class Router:
    def __init__(self, engine: PolicyEngine, adapters: Dict[str, ILlm]) -> None:
        self._engine = engine
        self._adapters = adapters

    def _pick_adapter(self, provider: str) -> ILlm:
        # exact provider match, else first adapter as default
        return self._adapters.get(provider) or next(iter(self._adapters.values()))

    def route(self, query: ModelQuery, context: PolicyContext = None) -> LlmResponse:
        if context is None:
            context = PolicyContext(query=query)
        # ADR-009 §10: estimate cost before deciding (conservative = max over catalog)
        if context.estimated_cost == 0.0:
            catalog = self._engine._registry.catalog()
            if catalog:
                est = max((estimate_cost(query, m) for m in catalog), default=0.0)
                context = replace(context, estimated_cost=est)
        decision = self._engine.decide(context)
        if not decision.allowed:
            return LlmResponse(
                text="",
                error=f"Policy veto: {decision.vetoed_by} — {decision.reason}",
            )
        adapter = self._pick_adapter(decision.selected_model.provider)
        return self._engine.execute(query, adapter, context)
