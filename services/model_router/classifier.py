"""LLM classifier — dynamic request typing via a lightweight local model (ТЗ-ECHO, E3).

Implements ``contracts.i_classifier.IClassifier``. Calls an ``ILlm`` (default phi3:mini via
Ollama) with a one-word classification prompt and parses the category. On any failure or
unparsable answer it returns ``None`` so the router falls back to rule-based routing
(graceful, LLM-01). A simple in-memory cache avoids re-calling the model for identical
prompts (optional; not persisted — E6 may add durable caching).

K1/K6: stdlib + contracts + services. Reuses ILlm / ModelQuery (no provider SDK; network
goes through the injected ILlm -> IHttpTransport). The classifier client is typically the
same IModelRouter the router uses, targeted at a small model via ``preferred_provider``.
"""

from __future__ import annotations

from typing import Dict, Optional

from contracts.i_classifier import IClassifier
from contracts.i_llm import ILlm, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout
from contracts.i_router_policy import IRouterPolicy

_PROMPT = (
    "Classify the user request into exactly one of these categories: "
    "code, creative, factual, analytical. "
    "Reply with ONE word only (the category name), nothing else."
)


class LLMClassifier(IClassifier):
    """Classify requests with a lightweight LLM; fall back to None on any issue."""

    def __init__(
        self,
        client: ILlm,
        model: str = "phi3:mini",
        cache: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout
        self._cache: Dict[str, str] = cache if cache is not None else {}

    def classify(self, query: ModelQuery) -> Optional[str]:
        prompt = query.prompt or ""
        if not prompt.strip():
            return None  # empty prompt -> let rule-based use default
        cached = self._cache.get(prompt)
        if cached is not None:
            return cached if cached in IRouterPolicy.CATEGORIES else None
        try:
            req = ModelQuery(
                prompt=_PROMPT + "\n\nRequest: " + prompt,
                preferred_provider=self._model,
                task="cheap",
            )
            resp = self._client.complete(req)
        except (LLMError, LLMTimeout):
            return None  # model unavailable -> rule-based fallback
        if resp is None or resp.error is not None:
            return None
        label = self._parse(resp.text)
        # cache only valid labels (None means "no confident answer" -> don't cache)
        if label is not None:
            self._cache[prompt] = label
        return label

    @staticmethod
    def _parse(text: str) -> Optional[str]:
        """Extract a single valid category token from the model's answer."""
        if not text:
            return None
        token = text.strip().split()[0].lower().strip(".,:;\"'")
        return token if token in IRouterPolicy.CATEGORIES else None

    def confidence(self, query: ModelQuery) -> float:
        # LLM classifier gives no structured confidence here; signal "present" only.
        return 0.0
