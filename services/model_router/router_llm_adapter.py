"""Thin ILlm adapter that exposes a RuleBasedRouter through the ILlm contract (ТЗ-ECHO, E1.4).

The kernel advisor only knows ``ILlm.complete(query) -> LlmResponse``. A ``RuleBasedRouter``
returns a richer ``RouterResult``. This adapter bridges them: ``complete`` delegates to
``router.route(RouterRequest(query))`` and returns ``result.response`` (a plain LlmResponse).
``stream`` is unsupported (raises NotImplementedError like the base contract default).

K1/K6: stdlib + contracts + services.model_router only. No provider SDK.
"""

from __future__ import annotations

from typing import Iterator, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError

from services.model_router.dtos import RouterRequest
from services.model_router.rule_based_router import RuleBasedRouter


class RouterAsLlm(ILlm):
    """Expose a ``RuleBasedRouter`` as an ``ILlm`` so the kernel advisor can call it unchanged."""

    def __init__(self, router: RuleBasedRouter) -> None:
        self._router = router
        # Surface the winning provider name for observability (LlmResponse.provider).
        self.provider = "echo-router"

    def complete(self, query: ModelQuery) -> LlmResponse:
        result = self._router.route(RouterRequest(query=query))
        resp = result.response
        # Annotate which routing path won (observability / E6 logging hook).
        if not resp.provider:
            resp = LlmResponse(
                text=resp.text,
                provider=self.provider,
                model=resp.model,
                actual_provider=resp.actual_provider,
                actual_model=resp.actual_model,
                trace_id=resp.trace_id,
                tokens=resp.tokens,
                tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                latency_ms=resp.latency_ms or result.latency_ms,
                cost=resp.cost or result.cost,
                error=resp.error,
            )
        return resp

    def stream(self, query: ModelQuery) -> Iterator[str]:
        raise NotImplementedError("Echo router does not support streaming yet (use complete())")
