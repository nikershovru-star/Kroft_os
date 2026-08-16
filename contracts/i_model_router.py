"""Model-router port for multi-provider LLM routing with fallback (ТЗ-OMNI-01, ADR-089).

K1-compliant: stdlib + contracts only. Reuses ``contracts.i_llm.ILlm`` as the underlying
transport (KROFT one-port-per-boundary: we do NOT introduce a second LLM port). The router
IS an ``ILlm`` (so ``adapter_for`` / the kernel advisor accept it unchanged) AND a
``IModelRouter`` (so callers can introspect the provider list and pick one explicitly).

OmniRouter (composition/omni_router.py) is the reference impl: an ordered list of
OpenAiCompatibleClient (one per ProviderSpec, sorted by priority), with complete() trying
each in priority order and falling back on LLMError/LLMTimeout; all failures -> LLMError
(graceful retrieval-only, LLM-01). Local Ollama first (detect_local_ollama), cloud only
when API keys are present (env).

K5: reuses ILlm / LlmResponse / ModelQuery / IHttpTransport / OpenAiCompatibleClient /
build_llm_client / detect_local_ollama. No new transport, no provider SDK in the domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery


@dataclass(frozen=True)
class ProviderSpec:
    """Declarative description of one LLM provider endpoint (ТЗ-OMNI-01).

    frozen VO (K1-clean). ``priority`` orders the fallback chain (lower = tried first).
    ``api_key_env`` names the ENV var holding the key; if the env var is empty, the
    provider is SKIPPED at build time (cloud only when keys present; local first).
    ``model`` defaults to ``"auto"`` (let the endpoint pick).
    """

    name: str
    base_url: str = ""             # empty allowed: routing-only specs (Echo policy) carry the
                                    # name; the real endpoint is resolved by the IModelRouter that
                                    # owns the live ILlm client (no fake URL in the routing layer).
    api_key_env: str = ""          # empty -> no key required (local/Ollama), else env var name
    priority: int = 100            # lower = tried first
    model: str = "auto"            # "auto" or explicit model id


class IModelRouter(ILlm):
    """Port: a multi-provider LLM router that is itself an ``ILlm`` (KROFT boundary reuse).

    A router exposes:
      - ``providers``: the ordered list of ProviderSpec (introspection / observability).
      - ``route(query) -> ILlm``: pick the provider that should answer (first healthy, by
        priority); returns an underlying ``ILlm`` client WITHOUT performing the call.
      - ``complete(query) -> LlmResponse``: inherited from ``ILlm`` — the impl tries
        providers in priority order, falling back on failure, raising ``LLMError`` only
        when ALL fail (caller falls back to retrieval-only, LLM-01).

    Contract:
      - Deterministic priority order (I-09): same provider list -> same attempt order.
      - On total failure MUST raise LLMError (NOT return a degraded response) so the
        kernel catches and goes LLM-free (graceful, no crash).
      - MUST NOT import a provider SDK; network I/O goes through IHttpTransport.
    """

    @property
    @abstractmethod
    def providers(self) -> List[ProviderSpec]:
        """Ordered provider specs (by priority)."""
        raise NotImplementedError

    @abstractmethod
    def route(self, query: ModelQuery) -> Optional[ILlm]:
        """Return the ILlm client that should answer ``query`` (first by priority), or None.

        Implementations may probe health (detect_local_ollama) but MUST stay deterministic
        and cheap; the actual call happens in ``complete``.
        """
        raise NotImplementedError

    # complete() is inherited abstract from ILlm — the impl provides it.
