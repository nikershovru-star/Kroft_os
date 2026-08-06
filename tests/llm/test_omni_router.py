"""ТЗ-OMNI-01 (ADR-089) — OmniRouter K8 tests (Флаг 1b, separate).

Covers: first healthy provider selected; priority fallback on failure; all-fail -> LLMError
(retrieval-only); deterministic priority order; K6 (no SDK in domain, transport via
IHttpTransport); empty router (no keys/model) raises LLMError, never crashes.

Uses an in-process FakeTransport (no live network / model). K5: reuses OpenAiCompatibleClient,
HttpTransport contract (IHttpTransport), build_omni_router, ProviderSpec.
"""

from __future__ import annotations

from typing import Optional

import pytest

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_http import HttpResponse, IHttpTransport, TransportError, TransportTimeout
from contracts.i_llm_advisor import LLMError, LLMTimeout
from contracts.i_model_router import IModelRouter, ProviderSpec

from adapters.openai_compatible import OpenAiCompatibleClient
from composition.omni_router import OmniRouter, build_omni_router
from composition.llm_client_factory import build_llm_client


class FakeTransport(IHttpTransport):
    """In-process transport: returns a canned OpenAI-style chat completion, or raises."""

    def __init__(self, mode: str = "ok", body: Optional[str] = None,
                 provider: str = "fake") -> None:
        self.mode = mode
        self.provider = provider
        self.last_url = None
        self.last_body = None
        self.calls = 0
        if body is None:
            self._body = ('{"model": "fake-model", "choices": [{"message": '
                          '{"content": "answer-from-' + provider + '"}}]}')
        else:
            self._body = body

    def request(self, method, url, headers=None, body=None, timeout=30.0):
        self.calls += 1
        self.last_url = url
        self.last_body = body
        if self.mode == "ok":
            return HttpResponse(status=200, body=self._body,
                                 headers={"x-omniroute-provider": self.provider})
        if self.mode == "error":
            raise TransportError("fake transport error")
        if self.mode == "timeout":
            raise TransportTimeout("fake transport timeout")
        raise TransportError("unknown fake mode")


def _client(name: str, mode: str = "ok", priority: int = 10) -> OpenAiCompatibleClient:
    return OpenAiCompatibleClient(
        base_url=f"http://{name}/v1",
        api_key="[REDACTED]",
        model="auto",
        transport=FakeTransport(mode=mode, provider=name),
        provider=name,
        timeout=5.0,
    )


def _spec(name: str, priority: int, api_key_env: str = "") -> ProviderSpec:
    return ProviderSpec(name=name, base_url=f"http://{name}/v1",
                         api_key_env=api_key_env, priority=priority, model="auto")


def test_omni_router_is_illm_and_model_router():
    r = OmniRouter([_client("a"), _client("b")], [_spec("a", 10), _spec("b", 20)])
    assert isinstance(r, ILlm)
    assert isinstance(r, IModelRouter)
    assert [p.name for p in r.providers] == ["a", "b"]


def test_first_healthy_provider_selected():
    """Both healthy -> first by priority answers (deterministic)."""
    r = OmniRouter([_client("a", mode="ok", priority=10),
                    _client("b", mode="ok", priority=20)],
                   [_spec("a", 10), _spec("b", 20)])
    resp = r.complete(ModelQuery(prompt="hi"))
    assert isinstance(resp, LlmResponse)
    assert "answer-from-a" in resp.text
    assert resp.provider == "a"


def test_fallback_on_failure():
    """First fails, second healthy -> second answers (priority fallback)."""
    r = OmniRouter([_client("a", mode="error", priority=10),
                    _client("b", mode="ok", priority=20)],
                   [_spec("a", 10), _spec("b", 20)])
    resp = r.complete(ModelQuery(prompt="hi"))
    assert "answer-from-b" in resp.text
    assert resp.provider == "b"


def test_all_fail_raises_llm_error_retrieval_only():
    """All providers fail -> LLMError (kernel falls back to retrieval-only, no crash)."""
    r = OmniRouter([_client("a", mode="error", priority=10),
                    _client("b", mode="timeout", priority=20)],
                   [_spec("a", 10), _spec("b", 20)])
    with pytest.raises(LLMError):
        r.complete(ModelQuery(prompt="hi"))


def test_deterministic_priority_order():
    """Stable sort: equal priorities keep insertion order; lower priority tried first."""
    # a(prio 20), b(prio 10) -> sorted b first, so b answers even though listed second.
    r = OmniRouter([_client("a", mode="ok", priority=20),
                    _client("b", mode="ok", priority=10)],
                   [_spec("a", 20), _spec("b", 10)])
    resp = r.complete(ModelQuery(prompt="hi"))
    assert resp.provider == "b"  # lower priority number tried first


def test_route_returns_first_by_priority():
    r = OmniRouter([_client("a", priority=20), _client("b", priority=10)],
                   [_spec("a", 20), _spec("b", 10)])
    chosen = r.route(ModelQuery(prompt="x"))
    assert chosen is not None
    # route returns the first client by priority (b), not by list order.
    resp = chosen.complete(ModelQuery(prompt="hi"))
    assert resp.provider == "b"


def test_empty_router_raises_llm_error_not_crash():
    """No providers (no keys/model) -> complete() raises LLMError, build never crashes."""
    r = build_omni_router([_spec("cloud", priority=10, api_key_env="NO_SUCH_KEY_123")],
                          include_local_ollama=False)
    assert r.providers == []  # cloud skipped (no key)
    with pytest.raises(LLMError):
        r.complete(ModelQuery(prompt="hi"))


def test_build_llm_client_backward_compat_single():
    """build_llm_client() without providers still returns a single ILlm (no router)."""
    c = build_llm_client()
    assert isinstance(c, ILlm)
    assert not isinstance(c, IModelRouter)  # single client, not a router


def test_build_llm_client_with_providers_returns_router():
    """build_llm_client(providers=...) returns an OmniRouter (multi-provider)."""
    r = build_llm_client(providers=[_spec("cloud", priority=10, api_key_env="NO_SUCH_KEY_456")])
    assert isinstance(r, IModelRouter)
    # cloud skipped (no key) + local Ollama not present on CI -> empty router, but valid;
    # adapter_for accepts it (router is an ILlm).
    from contracts.i_llm_advisor import adapter_for
    assert adapter_for(r) is not None


def test_k6_no_sdk_in_domain():
    """OmniRouter lives in composition/ and only depends on contracts + adapters (via port).

    The router never imports a provider SDK — network I/O is funneled through IHttpTransport.
    Assert the module does not reference forbidden SDK symbols.
    """
    import inspect
    import composition.omni_router as mod
    src = inspect.getsource(mod)
    for forbidden in ("import requests", "import httpx", "from openai", "import openai"):
        assert forbidden not in src, f"OmniRouter must not import SDK: {forbidden}"
