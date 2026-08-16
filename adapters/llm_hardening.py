"""LLM hardening — minimal retry/circuit/health layer on top of existing ILlm.

K1-compliant: stdlib + contracts only.
REUSE:
- contracts/i_llm.ILlm, LlmResponse, ModelQuery
- contracts/i_llm_advisor.LLMError, LLMTimeout
- services/retry_manager.py already provides IRetryManager-style bounded retries
  with route escalation; we reuse that concept here as a decorator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout


@dataclass
class ProviderHealth:
    provider: str
    model: str
    healthy: bool = True
    last_ping_ms: float = 0.0
    failure_quota: int = 0
    last_error: Optional[str] = None


class CircuitBreaker:
    """Minimal circuit breaker over a single provider/model target."""

    def __init__(self, threshold: int = 5, recovery_seconds: float = 30.0) -> None:
        self.threshold = max(1, int(threshold))
        self.recovery_seconds = max(0.0, float(recovery_seconds))
        self._failures = 0
        self._open_until = 0.0

    def allow(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        if self._open_until and now < self._open_until:
            return False
        if self._open_until and now >= self._open_until:
            self._open_until = 0.0
            self._failures = 0
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def record_failure(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self._failures += 1
        if self._failures >= self.threshold:
            self._open_until = now + self.recovery_seconds


class RetryableLlmClient(ILlm):
    """LLM client decorator with bounded retry and simple circuit breaker."""

    def __init__(self, inner: ILlm, max_attempts: int = 3) -> None:
        self._inner = inner
        self._max_attempts = max(1, int(max_attempts))
        self._breaker = CircuitBreaker()
        self._fallbacks: List[ILlm] = []
        self._health: List[ProviderHealth] = []

    def add_fallback(self, client: ILlm) -> None:
        self._fallbacks.append(client)

    def complete(self, query: ModelQuery) -> LlmResponse:
        last_error = None
        for attempt in range(1, self._max_attempts + 1):
            if not self._breaker.allow():
                last_error = LLMError("circuit open")
                continue
            try:
                response = self._inner.complete(query)
                self._breaker.record_success()
                return response
            except (LLMTimeout, LLMError) as exc:
                last_error = exc
                self._breaker.record_failure()
                continue
        for fallback in self._fallbacks:
            if not self._breaker.allow():
                continue
            try:
                return fallback.complete(query)
            except (LLMTimeout, LLMError):
                continue
        raise last_error or LLMError("llm unavailable")

    def stream(self, query: ModelQuery):
        yield self.complete(query).text


@dataclass
class LlmHealthCheck:
    clients: List[ILlm]
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def ping_all(self, probe: ModelQuery) -> List[ProviderHealth]:
        results: List[ProviderHealth] = []
        for client in self.clients:
            start = time.time()
            try:
                client.complete(probe)
                elapsed = (time.time() - start) * 1000.0
                results.append(ProviderHealth(provider="inner", model="probe", healthy=True, last_ping_ms=elapsed))
                self.breaker.record_success()
            except (LLMTimeout, LLMError) as exc:
                elapsed = (time.time() - start) * 1000.0
                results.append(ProviderHealth(provider="inner", model="probe", healthy=False, last_ping_ms=elapsed, last_error=str(exc)))
                self.breaker.record_failure()
        return results
