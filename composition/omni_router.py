"""OmniRouter — multi-provider LLM router with auto-select + fallback (ТЗ-OMNI-01, ADR-089).

Флаг C (composition root): may import contracts.* + adapters.* + composition.* (gate rule:
composition -> everything). Builds an ordered list of OpenAiCompatibleClient (one per
ProviderSpec, sorted by priority) over a shared IHttpTransport, tries them in order on
complete(), falls back on LLMError/LLMTimeout, and raises LLMError only when ALL fail
(graceful retrieval-only, LLM-01). Local Ollama is placed first (detect_local_ollama);
cloud providers are skipped when their API key env var is empty.

K1/K6: network I/O funnels through IHttpTransport (HttpTransport, stdlib urllib). No provider
SDK in the domain. I-09: deterministic priority order. O1: router is an advisor; failure ->
retrieval-only, the kernel stays LLM-free.

Reuses (K5, NO duplication): IHttpTransport, HttpTransport, OpenAiCompatibleClient,
detect_local_ollama, build_llm_client (all from existing modules).
"""

from __future__ import annotations

import os
from typing import List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_model_router import IModelRouter, ProviderSpec
from contracts.i_http import IHttpTransport, TransportError, TransportTimeout
from contracts.i_llm_advisor import LLMError, LLMTimeout

from adapters.http_transport import HttpTransport
from adapters.openai_compatible import OpenAiCompatibleClient


class OmniRouter(IModelRouter):
    """Reference IModelRouter: ordered providers, priority fallback, all-fail -> LLMError.

    ``clients`` MUST be aligned with ``specs`` (same order / same length) — element i of
    ``clients`` is the ILlm for ``specs[i]``. Both are sorted by priority at construction
    (stable sort) so route()/complete() attempt in a deterministic order.
    """

    def __init__(self, clients: List[ILlm], specs: List[ProviderSpec],
                 timeout: float = 30.0) -> None:
        if len(clients) != len(specs):
            raise ValueError("OmniRouter requires clients and specs to be 1:1")
        # stable sort by priority (lower = first); preserves insertion order on ties (I-09).
        ordered = sorted(range(len(specs)), key=lambda i: specs[i].priority)
        self._clients = [clients[i] for i in ordered]
        self._specs = [specs[i] for i in ordered]
        self._timeout = timeout

    @property
    def providers(self) -> List[ProviderSpec]:
        return list(self._specs)

    def route(self, query: ModelQuery) -> Optional[ILlm]:
        """Return the first client by priority (deterministic). None if no providers."""
        if not self._clients:
            return None
        return self._clients[0]

    def complete(self, query: ModelQuery) -> LlmResponse:
        if not self._clients:
            raise LLMError("OmniRouter has no providers configured (retrieval-only)")
        last: Optional[BaseException] = None
        for client in self._clients:
            try:
                return client.complete(query)
            except (LLMError, LLMTimeout) as exc:
                # transport/advisor failure -> try next provider (fallback by priority).
                last = exc
                continue
        # All providers failed: surface as LLMError so the kernel falls back to retrieval-only.
        raise LLMError(f"OmniRouter: all {len(self._clients)} providers failed "
                       f"(last: {last})")

    def stream(self, query: ModelQuery):
        """Yield completion chunks from the first provider that succeeds (priority fallback)."""
        if not self._clients:
            raise LLMError("OmniRouter has no providers configured (retrieval-only)")
        last: Optional[BaseException] = None
        for client in self._clients:
            try:
                for chunk in client.stream(query):
                    yield chunk
                return
            except (LLMError, LLMTimeout) as exc:
                last = exc
                continue
        raise LLMError(f"OmniRouter: all {len(self._clients)} providers failed "
                       f"(last: {last})")


def _env_has_key(spec: ProviderSpec) -> bool:
    """Cloud provider is usable only when its API key env var is set (non-empty)."""
    if not spec.api_key_env:
        return True  # local / keyless endpoint (e.g. Ollama)
    return bool(os.environ.get(spec.api_key_env, "").strip())


def build_omni_router(providers: List[ProviderSpec],
                      include_local_ollama: bool = True,
                      timeout: float = 30.0,
                      transport: Optional[IHttpTransport] = None) -> OmniRouter:
    """Build an OmniRouter from ProviderSpecs (composition helper, Флаг C).

    - Local Ollama (if include_local_ollama and detect_local_ollama()) is prepended with
      the lowest priority (tried FIRST) — keyless, offline-friendly default.
    - Cloud specs whose api_key_env is empty are SKIPPED (keys required to use them).
    - A shared HttpTransport backs every client (stdlib urllib, K6-clean).

    Returns an OmniRouter that may be empty (no providers) — callers handle that via the
    LLMError raised on complete() (retrieval-only), never a crash at build time.
    """
    specs: List[ProviderSpec] = []
    if include_local_ollama:
        try:
            from composition.llm_client_factory import detect_local_ollama
            if detect_local_ollama():
                specs.append(ProviderSpec(
                    name="local-ollama",
                    base_url="http://localhost:11434/v1",
                    api_key_env="",
                    priority=-100,  # lowest -> tried first
                    model="auto",
                ))
        except Exception:
            pass  # skip-if-unavailable: Ollama probe failure is not an error

    specs.extend(providers)

    clients: List[ILlm] = []
    used_specs: List[ProviderSpec] = []
    transport = transport or HttpTransport(default_timeout=timeout)
    for spec in specs:
        if not _env_has_key(spec):
            continue  # cloud without key -> skip
        clients.append(OpenAiCompatibleClient(
            base_url=spec.base_url,
            api_key=os.environ.get(spec.api_key_env, "") if spec.api_key_env else "[REDACTED]",
            model=spec.model,
            transport=transport,
            provider=spec.name,
            timeout=timeout,
        ))
        used_specs.append(spec)
    return OmniRouter(clients, used_specs, timeout=timeout)
