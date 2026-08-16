"""Router policy port — keyword/category routing rules for the Echo pattern (ТЗ-ECHO, E1/E2).

K1-compliant: stdlib + contracts only. Does NOT import a provider SDK or the LLM
transport — it maps a ``ModelQuery`` to a *category* and that category to a list of
``ProviderSpec`` (declared in contracts.i_model_router). The actual call is delegated
to an ``IModelRouter`` (composition/omni_router.py), so this port stays boundary-clean.

The router (services/model_router/rule_based_router.py) delegates execution to the
existing ``IModelRouter`` (OmniRouter) — we do NOT introduce a second LLM port (KROFT
one-port-per-boundary). This module only decides *where* a request should go.

K5: reuses ILlm / ModelQuery / ProviderSpec. No new transport.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from contracts.i_llm import ModelQuery
from contracts.i_model_router import ProviderSpec


class IRouterPolicy(ABC):
    """Port: decide which model(s) should answer a request, by rule.

    A policy maps a ``ModelQuery`` to a *category* label (code | creative | factual |
    analytical) and that category to an ordered list of ``ProviderSpec`` (the candidates
    to try, in priority order). It is pure decision logic — no network I/O.
    """

    # Canonical category labels (used by config/router_policy.yaml + classifier in E3).
    CATEGORIES = ("code", "creative", "factual", "analytical")

    @abstractmethod
    def classify(self, query: ModelQuery) -> str:
        """Return a category label (one of CATEGORIES) for ``query``.

        Rule-based impls match keywords; the E3 LLM-classifier falls back to this on
        unavailability. MUST return a valid label (never raise for a normal query).
        """
        raise NotImplementedError

    @abstractmethod
    def providers_for(self, category: str) -> List[ProviderSpec]:
        """Return the ordered candidate providers for ``category`` (empty list = none)."""
        raise NotImplementedError

    @abstractmethod
    def categories(self) -> List[str]:
        """Return all category labels known to this policy (for introspection/tests)."""
        raise NotImplementedError
