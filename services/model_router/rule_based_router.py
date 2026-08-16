"""Rule-based router — keyword -> category -> provider(s) -> response (ТЗ-ECHO, E2/E4).

Composition over inheritance: the router holds an ``IRouterPolicy`` (rule source) and an
``IModelRouter`` (the existing OmniRouter — transport/fallback selection). It does NOT
re-implement provider calling or fallback: it asks the policy *where* to go, then lets
the ``IModelRouter`` *execute* (priority fallback is OmniRouter's job). For multi-provider
categories it fans out via ``SimpleEnsembleOrchestrator``.

K1/K6: stdlib + contracts + services. No provider SDK; execution funnels through IModelRouter
-> ILlm -> IHttpTransport. The classifier (E3) plugs into ``classify`` later without touching
this file.
"""

from __future__ import annotations

import time
from typing import List, Optional

from contracts.i_ensemble_orchestrator import (
    IEnsembleOrchestrator,
    MergeStrategy,
)
from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_model_router import IModelRouter, ProviderSpec
from contracts.i_router_policy import IRouterPolicy

from services.model_router.dtos import RouterRequest, RouterResult
from services.model_router.ensemble_orchestrator import SimpleEnsembleOrchestrator


# Categories that should use the ensemble (parallel N models) instead of a single pick.
ENSEMBLE_CATEGORIES = {"analytical"}


class RuleBasedRouter(IRouterPolicy):
    """Routes by keyword/category rules; delegates execution to an IModelRouter.

    ``policy`` supplies classify() + providers_for(); ``router`` (an IModelRouter, e.g.
    OmniRouter) supplies the actual provider clients + priority fallback. ``ensemble``
    (default SimpleEnsembleOrchestrator) is used when a category maps to >1 provider or
    when ``force_ensemble=True``.
    """

    def __init__(
        self,
        policy: IRouterPolicy,
        router: IModelRouter,
        ensemble: Optional[IEnsembleOrchestrator] = None,
        ensemble_categories: Optional[frozenset] = None,
    ) -> None:
        self._policy = policy
        self._router = router
        self._ensemble = ensemble or SimpleEnsembleOrchestrator()
        self._ensemble_categories = ensemble_categories or ENSEMBLE_CATEGORIES

    # --- IRouterPolicy delegation (this object IS the policy surface) ---
    def classify(self, query: ModelQuery) -> str:
        return self._policy.classify(query)

    def providers_for(self, category: str) -> List[ProviderSpec]:
        return self._policy.providers_for(category)

    def categories(self) -> List[str]:
        return self._policy.categories()

    # --- routing ---
    def route(self, req: RouterRequest, force_ensemble: bool = False) -> RouterResult:
        """Classify (if needed), pick providers, execute single or ensemble."""
        t0 = time.perf_counter()
        category = req.category or self._policy.classify(req.query)
        specs = self._policy.providers_for(category)

        # Map specs -> live ILlm clients from the underlying IModelRouter.
        clients = self._clients_for_specs(specs)

        if not clients:
            # No provider for this category -> retrieval-only signal (LLM-01).
            wall = (time.perf_counter() - t0) * 1000.0
            return RouterResult(
                response=LlmResponse(text="", error=f"router: no provider for '{category}'"),
                category=category,
                chosen_providers=[],
                latency_ms=wall,
                cost=0.0,
                used_ensemble=False,
            )

        use_ensemble = force_ensemble or (category in self._ensemble_categories and len(clients) > 1)
        if use_ensemble:
            result = self._ensemble.run(req.query, clients, strategy=MergeStrategy.BEST_CONFIDENCE)
            wall = (time.perf_counter() - t0) * 1000.0
            return RouterResult(
                response=result.response,
                category=category,
                chosen_providers=[getattr(c, "provider", "?") for c in clients],
                latency_ms=wall,
                cost=result.cost,
                used_ensemble=True,
            )

        # Single-model path: let the IModelRouter do priority fallback on one spec.
        chosen = clients[0]
        try:
            resp = chosen.complete(req.query)
        except Exception as exc:  # router must be graceful, never crash the kernel
            resp = LlmResponse(text="", error=f"router single failed: {exc}")
        wall = (time.perf_counter() - t0) * 1000.0
        return RouterResult(
            response=resp,
            category=category,
            chosen_providers=[getattr(chosen, "provider", "?")],
            latency_ms=wall,
            cost=resp.cost,
            used_ensemble=False,
        )

    def _clients_for_specs(self, specs: List[ProviderSpec]) -> List[ILlm]:
        """Resolve ProviderSpecs to live ILlm clients via the IModelRouter public API (G3 fix).

        Uses ``router.client_for(name)`` — the single canonical name->client resolution
        point (no private ``_clients`` access, K1-clean). Unknown provider names are
        skipped (controlled, no KeyError/None.complete). Duplicate names are de-duplicated
        (G8: per_model dict would otherwise drop a result).
        """
        clients: List[ILlm] = []
        seen: set = set()
        for spec in specs:
            if spec.name in seen:
                continue  # dedupe provider names (G8)
            seen.add(spec.name)
            c = self._router.client_for(spec.name)
            if c is not None:
                clients.append(c)
        if not clients and self._router.providers:
            # Fallback: no name matched -> use the router's first-by-priority client so a
            # single-provider deployment still answers (graceful, deterministic).
            first = self._router.route(self._dummy_query())
            if first is not None:
                clients.append(first)
        return clients

    @staticmethod
    def _dummy_query() -> ModelQuery:
        return ModelQuery(prompt="")
