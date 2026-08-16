"""Tests: adapters/llm_hardening.py."""

from __future__ import annotations

from adapters.llm_hardening import CircuitBreaker, LlmHealthCheck, RetryableLlmClient
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout


class FakeLlm:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls += 1
        resp = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def stream(self, query: ModelQuery):
        yield self.complete(query).text


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(threshold=2, recovery_seconds=10.0)
    assert breaker.allow()
    breaker.record_failure(now=1000.0)
    assert breaker.allow()
    breaker.record_failure(now=1000.0)
    assert not breaker.allow(now=1000.0)


def test_retryable_client_retries_and_returns():
    inner = FakeLlm([LLMTimeout("t"), LlmResponse(text="ok", actual_model="m")])
    client = RetryableLlmClient(inner, max_attempts=3)
    response = client.complete(ModelQuery(prompt="hi"))
    assert response.text == "ok"
    assert inner.calls == 2


def test_retryable_client_falls_back_after_exhaustion():
    inner = FakeLlm([LLMError("x"), LLMError("x"), LLMError("x")])
    fallback = FakeLlm([LlmResponse(text="fallback", actual_model="f")])
    client = RetryableLlmClient(inner, max_attempts=3)
    client.add_fallback(fallback)
    response = client.complete(ModelQuery(prompt="hi"))
    assert response.text == "fallback"
    assert inner.calls == 3
    assert fallback.calls == 1


def test_retryable_client_raises_when_all_fail():
    inner = FakeLlm([LLMError("x")])
    fallback = FakeLlm([LLMError("y")])
    client = RetryableLlmClient(inner, max_attempts=2)
    client.add_fallback(fallback)
    try:
        client.complete(ModelQuery(prompt="hi"))
    except LLMError:
        pass
    else:
        raise AssertionError("expected LLMError")
