"""LLM client composition (ТЗ-LLM-LIVE-01, ADR-079) — standalone, Флаг C (НЕ in build_kernel).

Wires the real HTTP transport (adapters/http_transport.py: HttpTransport) to the LLM-02
OpenAI-compatible client (adapters/openai_compatible.py: OpenAiCompatibleClient) into a
ready-to-use ``ILlm`` bound to a concrete local/model endpoint.

K3/K6: this is the ONLY place that assembles concrete adapters — ``composition.* -> everything``
(gate rule). The kernel imports only the ``ILLMAdvisor`` port + ``adapter_for`` (LLM-01); it never
touches this factory or any provider SDK. The transport/client live in ``adapters/`` (K6-clean).

No live model required to build the client — ``base_url`` may point at Ollama (localhost:11434/v1),
LM Studio, vLLM, or any OpenAI-compatible gateway. ``detect_local_ollama`` is a best-effort probe.
"""

from __future__ import annotations

from typing import List, Optional

from adapters.http_transport import HttpTransport
from adapters.openai_compatible import OpenAiCompatibleClient
from contracts.i_llm import ILlm
from contracts.i_model_router import ProviderSpec


def build_llm_client(
    base_url: str = "http://localhost:11434/v1",
    model: str = "auto",
    api_key: str = "[REDACTED]",
    timeout: float = 30.0,
    providers: Optional[List[ProviderSpec]] = None,
) -> ILlm:
    """Standalone factory (Флаг C): real HTTP transport + OpenAI-compatible LLM client.

    Returns an ``ILlm`` (OpenAiCompatibleClient) whose network I/O goes through a real
    ``HttpTransport`` (stdlib urllib). On transport failure the client raises LLMTimeout/
    LLMError, which the LLM-01 advisor bridge maps to graceful kernel fallback.

    ТЗ-OMNI-01: if ``providers`` is given (non-empty), build a multi-provider ``OmniRouter``
    instead (auto-select + priority fallback; local Ollama first, cloud only with keys). The
    router is itself an ``ILlm``, so ``adapter_for`` / the kernel accept it unchanged.
    """
    if providers:
        from composition.omni_router import build_omni_router
        return build_omni_router(providers, include_local_ollama=True, timeout=timeout)
    transport = HttpTransport(base_url, default_timeout=timeout)
    return OpenAiCompatibleClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        transport=transport,
        provider="openai-compatible",
        timeout=timeout,
    )


def detect_local_ollama(host: str = "http://localhost:11434", timeout: float = 2.0) -> bool:
    """Best-effort probe: is an Ollama-compatible /models endpoint reachable on ``host``?

    Used to auto-pick a local model endpoint when available. Returns False on any failure
    (no model, refused, timeout) — the caller falls back to another endpoint or LLM-free.
    """
    try:
        req = urllib.request.Request(f"{host.rstrip('/')}/api/tags",
                                    headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — probe is best-effort
        return False
