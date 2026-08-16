"""LLM classifier port — dynamic request typing for the Echo pattern (ТЗ-ECHO, E3).

K1-compliant: stdlib + contracts only. A classifier maps a ``ModelQuery`` to a *category*
label (code | creative | factual | analytical), optionally with a confidence. It is the
dynamic counterpart of ``IRouterPolicy.classify`` (rule-based): the router tries the
classifier first and falls back to the rule policy when the classifier is unavailable.

Contract:
  - ``classify(query) -> Optional[str]``: return a valid category label, or ``None`` when
    the classifier cannot answer (LLM unavailable / unparsable / errored) so the router
    falls back to rule-based routing. MUST NOT raise on a normal query.
  - ``confidence(query) -> float``: 0.0..1.0 proxy; default 0.0 (optional signal for E4/E5).
  - No network I/O in the port itself; the impl uses an ``ILlm``.

K5: reuses ILlm / ModelQuery / IRouterPolicy.CATEGORIES. No new transport, no provider SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from contracts.i_llm import ModelQuery
from contracts.i_router_policy import IRouterPolicy


class IClassifier(ABC):
    """Port: dynamic request classification (LLM-based), with rule-based fallback."""

    # Valid labels (mirror IRouterPolicy.CATEGORIES for consistency).
    CATEGORIES = IRouterPolicy.CATEGORIES

    @abstractmethod
    def classify(self, query: ModelQuery) -> Optional[str]:
        """Return a category label, or None to trigger rule-based fallback.

        Implementations MUST return either a member of ``CATEGORIES`` or ``None``. On any
        failure (LLM error, timeout, unparsable answer) return None — never raise into the
        router (graceful degradation, LLM-01 style).
        """
        raise NotImplementedError

    def confidence(self, query: ModelQuery) -> float:
        """Optional confidence proxy in [0, 1]; default 0.0 (router ignores if unknown)."""
        return 0.0
