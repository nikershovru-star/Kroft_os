"""PolicyEngine — orchestrator (Wave 5, ADR-009 §6).

Runs the Rule Evaluation Pipeline:
  Phase 1  Veto check      (can_veto policies, ascending priority)
  Phase 2  Catalog filter   (non-veto policies narrow the catalog)
  Phase 3  Ranking         (ProviderSelectionPolicy orders candidates)
  Phase 4  Fallback chain  (top-N from ranked list)
  Phase 5  Execution+retry  (via FallbackPolicy wrapper around ILlm)

The engine knows nothing about rule semantics — policies decide.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision
from contracts.model_registry import ModelRegistry


class FallbackPolicy:
    """Runtime wrapper around ILlm.complete() (ADR-009 §4.5). Not part of evaluate()."""

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay_ms: float = 500.0,
        degrade_to_cheap: bool = True,
        offline_fallback: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.degrade_to_cheap = degrade_to_cheap
        self.offline_fallback = offline_fallback

    def should_retry(self, exc) -> bool:
        """Transient errors (429/5xx/timeout) are retryable; auth/4xx are not."""
        msg = str(exc).lower()
        if any(k in msg for k in ("401", "403", "404", "invalid", "unauthorized", "forbidden")):
            return False
        return any(k in msg for k in ("429", "500", "502", "503", "504", "timeout", "rate"))


class PolicyEngine:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry
        self._policies: List[IPolicy] = []
        self._fallback = FallbackPolicy()

    def register(self, policy: IPolicy) -> None:
        self._policies.append(policy)
        self._policies.sort(key=lambda p: p.priority)

    # --- Phase 1-4: decision ------------------------------------------------
    def decide(self, context: PolicyContext) -> PolicyDecision:
        catalog = list(self._registry.catalog())

        # Phase 1: Veto
        for p in sorted(self._policies, key=lambda p: p.priority):
            if not p.can_veto:
                continue
            d = p.evaluate(context, catalog)
            if not d.allowed:
                return PolicyDecision(
                    allowed=False,
                    vetoed_by=p.name,
                    reason=d.reason,
                    audit_log=[f"{p.name}: {r}" for r in d.audit_log],
                    constraints_applied=[p.name],
                )

        # Phase 2-3: Filter + Rank
        filtered = list(catalog)
        rankings: Dict[str, float] = {m.id: 0.0 for m in filtered}
        for p in self._policies:
            if p.can_veto:
                continue
            d = p.evaluate(context, filtered)
            # filter: keep only models the policy kept in its fallback_chain
            if d.fallback_chain:
                keep = {m.id for m in d.fallback_chain}
                filtered = [m for m in filtered if m.id in keep]
                # ranking: order in fallback_chain => higher score for earlier
                for idx, m in enumerate(d.fallback_chain):
                    rankings[m.id] = max(rankings.get(m.id, 0.0), (len(d.fallback_chain) - idx))

        if not filtered:
            return PolicyDecision(allowed=False, reason="No models satisfy all policies")

        sorted_models = sorted(filtered, key=lambda m: rankings.get(m.id, 0.0), reverse=True)
        return PolicyDecision(
            allowed=True,
            selected_model=sorted_models[0],
            fallback_chain=sorted_models[1:4],
            reason=f"Selected {sorted_models[0].id} via PolicyEngine",
            audit_log=[f"engine: {len(sorted_models)} candidates ranked"],
            constraints_applied=[p.name for p in self._policies],
        )

    # --- Phase 5: execution + retry ----------------------------------------
    def execute(self, query: ModelQuery, adapter: ILlm, context: Optional[PolicyContext] = None) -> LlmResponse:
        if context is None:
            context = PolicyContext(query=query)
        decision = self.decide(context)

        if not decision.allowed:
            return LlmResponse(text="", error=f"Policy veto: {decision.vetoed_by} — {decision.reason}")

        models_to_try = [decision.selected_model] + list(decision.fallback_chain)
        last_error = ""
        for model in models_to_try:
            routed = ModelQuery(
                task=query.task,
                reasoning=query.reasoning,
                local=query.local,
                json_mode=query.json_mode,
                cheap=query.cheap,
                context_window=query.context_window,
                preferred_provider=model.id,
                prompt=query.prompt,
            )
            try:
                resp = adapter.complete(routed)
                if resp.ok():
                    return resp
                last_error = resp.error or "unknown"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if not self._fallback.should_retry(exc):
                    break

        return LlmResponse(text="", error=f"All fallbacks exhausted. Last: {last_error}")
