"""OpenAI-compatible Model Platform client (MVP, candidate ADR-033).

Stdlib urllib only — zero external deps, mirrors OpenAIEmbeddingAdapter.
Points at any OpenAI-compatible endpoint (OmniRoute, LiteLLM, LM Studio, ...).
Domain layer never imports this directly; it depends on contracts.ILlm.
"""
from __future__ import annotations

import json
import time
import urllib.request
import uuid
from typing import Iterator, List, Optional

from contracts.i_llm import ILlm, IModelMetadata, IHealth, LlmResponse, ModelInfo, ModelQuery


class OpenAiCompatibleClient(ILlm, IModelMetadata, IHealth):
    """Minimal OpenAI-compatible chat completion client.

    base_url: e.g. "http://localhost:20128/v1" (OmniRoute) or
              "http://localhost:11434/v1" (Ollama).
    api_key:  any string — keyless gateways accept anything (OmniRoute accepts
             any non-empty value; default "[REDACTED]" avoids leaking a real key).
    model:    requested model id, or "auto" when the gateway routes for us.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:20128/v1",
        api_key: str = "[REDACTED]",
        model: str = "auto",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # declared catalog is empty by default; subclasses/registry fill it.
        self._catalog: List[ModelInfo] = []
        self._stats = {"calls": 0, "errors": 0, "total_latency_ms": 0.0}

    # --- ILlm ---------------------------------------------------------------
    def complete(self, query: ModelQuery) -> LlmResponse:
        trace_id = uuid.uuid4().hex[:16]
        model = query.preferred_provider or self.model
        t0 = time.monotonic()
        self._stats["calls"] += 1
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": query.prompt}],
                "stream": False,
            }
            if query.json_mode:
                payload["response_format"] = {"type": "json_object"}
            data = self._post("/chat/completions", payload)
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens = int(usage.get("total_tokens", 0))
            tokens_in = int(usage.get("prompt_tokens", 0))
            tokens_out = int(usage.get("completion_tokens", 0))
            # Gateway routing truth (Wave 6): prefer authoritative response
            # headers over the body's `model` field when present.
            hdr = data.get("_headers", {})
            actual_provider = (
                hdr.get("x-omniroute-provider")
                or hdr.get("x-provider")
                or ""
            )
            actual_model = (
                hdr.get("x-omniroute-model")
                or hdr.get("x-model")
                or data.get("model", model)
            )
            decision = hdr.get("x-omniroute-decision", "")
            self._stats["total_latency_ms"] += (time.monotonic() - t0) * 1000
            return LlmResponse(
                text=text,
                trace_id=trace_id,
                provider=self.base_url,
                model=model,
                actual_provider=actual_provider,
                actual_model=actual_model,
                decision=decision,
                tokens=tokens,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                cost=0.0,
            )
        except Exception as exc:  # noqa: BLE001 — normalize all failures
            self._stats["errors"] += 1
            return LlmResponse(
                text="",
                trace_id=trace_id,
                provider=self.base_url,
                model=model,
                actual_model="",
                error=f"{type(exc).__name__}: {exc}",
            )

    def stream(self, query: ModelQuery) -> Iterator[str]:
        # Default: non-streaming wrapped. Real SSE streaming is a Wave-6 concern.
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
        try:
            self._get("/models")
            return True
        except Exception:  # noqa: BLE001
            return False

    def stats(self) -> dict:
        return dict(self._stats)

    # --- transport ----------------------------------------------------------
    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            # capture response headers for gateway routing truth (Wave 6)
            headers = {k.lower(): v for k, v in resp.getheaders()}
            body["_headers"] = headers
            return body

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
