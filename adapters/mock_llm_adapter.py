"""(adapters) MockLlmAdapter — deterministic LLM for offline / fallback (Bootstrap).

This is the MANDATORY fallback LLM. When no external backend (OmniRoute @:20128)
is reachable, the OS must still boot and answer. MockLlmAdapter implements the
same contracts.i_llm.ILlm surface as OmniRouteAdapter so it is a drop-in: the
Router/executor cannot tell the difference at the port level.

Deterministic by design: given a prompt it returns a stable, template-based
answer (never calls the network). ping() is always True so the LLM factory
treats it as perpetually available.
"""
from __future__ import annotations

import time
import uuid
from typing import Iterator, List, Optional

from contracts.i_llm import ILlm, IModelMetadata, IHealth, LlmResponse, ModelInfo, ModelQuery

MOCK_MODEL = ModelInfo(
    id="mock-local",
    provider="mock",
    reasoning=False,
    context_window=8192,
    free=True,
)


class MockLlmAdapter(ILlm, IModelMetadata, IHealth):
    """Offline, deterministic LLM. Always healthy. No network."""

    def __init__(self, model: str = "mock-local", latency_ms: float = 5.0) -> None:
        self.model = model
        self._latency_ms = latency_ms
        self._catalog: List[ModelInfo] = [MOCK_MODEL]
        self._stats = {"calls": 0, "errors": 0, "total_latency_ms": 0.0}

    # --- ILlm ---------------------------------------------------------------
    def complete(self, query: ModelQuery) -> LlmResponse:
        trace_id = uuid.uuid4().hex[:16]
        self._stats["calls"] += 1
        t0 = time.monotonic()
        prompt = (query.prompt or "").strip()
        # Deterministic echo-style answer so smoke tests are reproducible.
        if not prompt:
            text = "[mock] empty prompt received"
        else:
            text = (
                f"[mock:{self.model}] ack: {prompt[:160]}"
            )
        self._stats["total_latency_ms"] += (time.monotonic() - t0) * 1000
        return LlmResponse(
            text=text,
            trace_id=trace_id,
            provider="mock",
            model=self.model,
            actual_provider="mock",
            actual_model=self.model,
            decision="mock",
            tokens=len(text.split()),
            tokens_in=len((query.prompt or "").split()),
            tokens_out=len(text.split()),
            latency_ms=self._latency_ms,
            cost=0.0,
        )

    def stream(self, query: ModelQuery) -> Iterator[str]:
        resp = self.complete(query)
        if resp.error:
            yield f"[ERROR] {resp.error}"
            return
        yield resp.text

    # --- IModelMetadata -----------------------------------------------------
    def catalog(self) -> List[ModelInfo]:
        return list(self._catalog)

    def capabilities(self, model_id: str) -> Optional[ModelInfo]:
        for m in self._catalog:
            if m.id == model_id:
                return m
        return None

    def register_model(self, info: ModelInfo) -> None:
        self._catalog.append(info)

    # --- IHealth ------------------------------------------------------------
    def ping(self) -> bool:
        # Mock is always available — it is the offline fallback.
        return True

    def stats(self) -> dict:
        return dict(self._stats)
