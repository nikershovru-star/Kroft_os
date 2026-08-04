"""HTTP transport port for swappable provider adapters (ТЗ-LLM-02, ADR-068).

K1-compliant: stdlib + contracts only. Concrete provider adapters (OpenAI-compatible,
OmniRoute, Ollama) depend on THIS port for network I/O — they MUST NOT import
``requests``/``httpx``/provider SDKs in the domain layer (K6). The network boundary is
funneled through ``IHttpTransport`` so test doubles (fake transports) can exercise the
adapter without any live network or model.

This is a SEPARATE boundary from ``contracts/i_llm.ILlm`` (the model port) and from
``contracts/i_telemetry.py`` (system metrics) and ``contracts/i_observability.py``
(live runtime metrics) — KROFT one-port-per-boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class HttpResponse:
    """Normalized HTTP response (provider-agnostic)."""
    status: int
    body: str
    headers: Dict[str, str] = field(default_factory=dict)


class IHttpTransport(ABC):
    """Port: make an HTTP request and return a normalized ``HttpResponse``.

    Concrete transports may wrap ``requests``/``httpx``/``urllib``/a custom socket — but
    that is THEIR implementation detail, hidden behind this port. Adapters (ILlm) call
    ``request`` and never touch a provider SDK directly.
    """

    @abstractmethod
    def request(self, method: str, url: str,
                headers: Optional[Dict[str, str]] = None,
                body: Optional[str] = None,
                timeout: float = 30.0) -> HttpResponse:
        """Perform an HTTP request.

        Raises:
            TransportError: connection refused / DNS / 5xx / non-2xx payload.
            TransportTimeout: the request exceeded ``timeout``.
        Must NOT raise generic ``Exception`` for network conditions the adapter must
        map to ``LLMError``/``LLMTimeout`` — raise the typed transport errors below so
        the adapter's mapping is unambiguous.
        """
        raise NotImplementedError


class TransportError(Exception):
    """Network-level failure (connection refused, 5xx, malformed response)."""


class TransportTimeout(Exception):
    """The request exceeded its timeout budget."""
