"""OpenAI-compatible concrete ILlm adapter (ТЗ-LLM-02, ADR-068) — LLM-FREE of provider SDK.

K1/K6: depends ONLY on contracts (i_llm, i_http, i_llm_advisor error vocabulary) + stdlib.
It does NOT import ``requests``/``httpx``/``openai`` — network I/O goes through the
``IHttpTransport`` port, so the adapter is fully testable with a fake transport (no live
network or model needed in CI).

The adapter maps transport failures to the advisor error vocabulary so the LLM-01
kernel bridge (``adapter_for`` -> ``ILLMAdvisor`` -> kernel fallback) handles them
gracefully:
  - TransportTimeout  -> LLMTimeout
  - TransportError    -> LLMError
  - non-2xx / bad JSON -> LLMError
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_http import (
    HttpResponse,
    IHttpTransport,
    TransportError,
    TransportTimeout,
)
from contracts.i_llm_advisor import LLMError, LLMTimeout


class OpenAiCompatibleClient(ILlm):
    """Concrete ``ILlm`` speaking the OpenAI /chat/completions wire format.

    Works against any OpenAI-compatible endpoint (OpenAI, vLLM, LM Studio, local
    gateways) by swapping the injected ``IHttpTransport``. ``actual_model`` is always
    set (ADR-065 double-routing observability): it equals the requested ``model`` for a
    direct client, or the gateway-resolved model when headers report one.
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 transport: IHttpTransport,
                 provider: str = "openai-compatible",
                 timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._transport = transport
        self._provider = provider
        self._timeout = timeout

    # -- ILlm ---------------------------------------------------------------
    def complete(self, query: ModelQuery) -> LlmResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": query.prompt}],
            "temperature": 0.2,
            "max_tokens": 512,  # Ollama висит без явного лимита (генерирует до контекста)
        }
        if query.json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = self._transport.request(
                "POST", url, headers=headers,
                body=json.dumps(payload), timeout=self._timeout)
        except TransportTimeout as e:
            raise LLMTimeout(f"openai-compatible timeout: {e}") from e
        except TransportError as e:
            raise LLMError(f"openai-compatible transport error: {e}") from e

        if resp.status < 200 or resp.status >= 300:
            raise LLMError(f"openai-compatible non-2xx {resp.status}: {resp.body[:200]}")

        try:
            data = json.loads(resp.body)
            content = data["choices"][0]["message"]["content"]
            actual_model = data.get("model") or self._model
            headers_lower = {k.lower(): v for k, v in (resp.headers or {}).items()}
            actual_provider = headers_lower.get("x-omniroute-provider") or self._provider
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise LLMError(f"openai-compatible malformed response: {e}") from e

        return LlmResponse(
            text=content,
            provider=self._provider,
            model=self._model,
            actual_provider=actual_provider,
            actual_model=actual_model,  # mandatory (ADR-065 double-routing)
        )

    def stream(self, query: ModelQuery) -> Iterator[str]:
        # Reference default: single completion, yielded as one chunk. Concrete adapters
        # may override with SSE parsing, but the contract only requires an iterator.
        yield self.complete(query).text
