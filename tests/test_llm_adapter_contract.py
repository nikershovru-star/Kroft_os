"""K8 contract-tests for ТЗ-LLM-02 — concrete OpenAI-compatible ILlm adapter (no live model).

Covers (acceptance + O1/K1/K6/K8 + ADR-068):
- adapter satisfies ILlm via fake IHttpTransport: success -> LlmResponse with actual_model.
- adapter_for(ILlm) -> ILLMAdvisor -> LLMAdvice (suggestion + confidence).
- transport error -> LLMError -> kernel graceful fallback == result WITHOUT LLM.
- timeout -> LLMTimeout -> kernel fallback == result WITHOUT LLM.
- llm.fallback_rate increments on fallback (closes Флаг 2 OBS-01).
- existing LLM-01 / OBS-01 tests remain green (run separately).

Transport boundary: the adapter imports ONLY contracts + stdlib (no requests/httpx);
network I/O goes through the injected IHttpTransport (K6). All tests use a FAKE transport
— no network, no model, no API key.
"""

from __future__ import annotations

from contracts.i_http import (
    HttpResponse,
    IHttpTransport,
    TransportError,
    TransportTimeout,
)
from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import (
    AdviseContext,
    ILLMAdvisor,
    LLMError,
    LLMTimeout,
    adapter_for,
)
from contracts.i_observability import ILiveMetricsCollector, METRIC_LLM_FALLBACK_RATE
from adapters.openai_compatible import OpenAiCompatibleClient
from kernel.cognitive_kernel import build_kernel
from kernel.observability import LiveMetricsCollector
from kernel.execution import ReferenceExecutor
from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    NodeLamportClock,
    Provenance,
    ProvenanceType,
)


class _OkTransport(IHttpTransport):
    def __init__(self, body):
        self._body = body
    def request(self, method, url, headers=None, body=None, timeout=30.0):
        return HttpResponse(200, self._body, {"x-omniroute-provider": "openai"})


class _FailingTransport(IHttpTransport):
    def request(self, method, url, headers=None, body=None, timeout=30.0):
        raise TransportError("connection refused")


class _TimeoutTransport(IHttpTransport):
    def request(self, method, url, headers=None, body=None, timeout=30.0):
        raise TransportTimeout("took too long")


def _client(transport):
    return OpenAiCompatibleClient("http://fake/v1", "key", "gpt-4o", transport)


# ---------------------------------------------------------------------------
# 1. adapter satisfies ILlm (fake transport): success -> LlmResponse(actual_model)
# ---------------------------------------------------------------------------
def test_adapter_satisfies_ilm_success():
    body = '{"choices":[{"message":{"content":"pick blue"}}],"model":"gpt-4o"}'
    c = _client(_OkTransport(body))
    assert isinstance(c, ILlm)
    r = c.complete(ModelQuery(prompt="go"))
    assert isinstance(r, LlmResponse)
    assert r.actual_model == "gpt-4o"          # mandatory (ADR-065 double-routing)
    assert r.actual_provider == "openai"       # gateway header honored
    assert r.text == "pick blue"


# ---------------------------------------------------------------------------
# 2. adapter_for(ILlm) -> ILLMAdvisor -> LLMAdvice
# ---------------------------------------------------------------------------
def test_adapter_for_yields_llm_advice():
    body = '{"choices":[{"message":{"content":"choose_blue"}}]}'
    advisor = adapter_for(_client(_OkTransport(body)))
    assert isinstance(advisor, ILLMAdvisor)
    ctx = AdviseContext(
        intent_text="go for blue", world_facts=("f",), candidate_descriptions=("choose_blue",))
    advice = advisor.advise(ctx)
    assert advice is not None
    assert getattr(advice, "suggestion", "") == "choose_blue"
    assert isinstance(getattr(advice, "confidence", None), ConfidenceScore)


# ---------------------------------------------------------------------------
# 3. transport error -> LLMError -> kernel fallback == result WITHOUT LLM
# ---------------------------------------------------------------------------
def test_transport_error_falls_back_to_no_llm():
    client = _client(_FailingTransport())
    k = build_kernel("LLM-E", llm_client=client)
    k.attach_executor(ReferenceExecutor())
    no_llm = build_kernel("LLM-E0")
    no_llm.attach_executor(ReferenceExecutor())
    it = Intent(id="i", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="u", actor="u"))
    a = k.tick(it)
    b = no_llm.tick(it)
    # graceful fallback: identical outcome with or without (failing) advisor
    assert a == b


def test_transport_error_raises_llmerror():
    client = _client(_FailingTransport())
    advisor = adapter_for(client)
    ctx = AdviseContext(intent_text="go", world_facts=(), candidate_descriptions=())
    try:
        advisor.advise(ctx)
        assert False, "must raise"
    except LLMError:
        pass


# ---------------------------------------------------------------------------
# 4. timeout -> LLMTimeout -> kernel fallback == result WITHOUT LLM
# ---------------------------------------------------------------------------
def test_timeout_falls_back_to_no_llm():
    client = _client(_TimeoutTransport())
    k = build_kernel("LLM-T", llm_client=client)
    k.attach_executor(ReferenceExecutor())
    no_llm = build_kernel("LLM-T0")
    no_llm.attach_executor(ReferenceExecutor())
    it = Intent(id="i", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="u", actor="u"))
    a = k.tick(it)
    b = no_llm.tick(it)
    assert a == b


def test_timeout_raises_llmtimeout():
    client = _client(_TimeoutTransport())
    advisor = adapter_for(client)
    ctx = AdviseContext(intent_text="go", world_facts=(), candidate_descriptions=())
    try:
        advisor.advise(ctx)
        assert False, "must raise"
    except LLMTimeout:
        pass


# ---------------------------------------------------------------------------
# 5. llm.fallback_rate increments on fallback (Флаг 2 OBS-01)
# ---------------------------------------------------------------------------
def test_fallback_rate_increments_on_failure():
    c = LiveMetricsCollector(NodeLamportClock("LLM-F"))
    client = _client(_FailingTransport())
    k = build_kernel("LLM-F", llm_client=client, live_metrics=c)
    k.attach_executor(ReferenceExecutor())
    assert isinstance(c, ILiveMetricsCollector)
    it = Intent(id="i", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="u", actor="u"))
    for _ in range(3):
        k.tick(it)
    assert c.ratio(METRIC_LLM_FALLBACK_RATE) == 1.0  # 3 failures / 3 attempts


def test_fallback_rate_zero_when_no_failures():
    c = LiveMetricsCollector(NodeLamportClock("LLM-F0"))
    body = '{"choices":[{"message":{"content":"x"}}]}'
    client = _client(_OkTransport(body))
    k = build_kernel("LLM-F0", llm_client=client, live_metrics=c)
    k.attach_executor(ReferenceExecutor())
    it = Intent(id="i", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="u", actor="u"))
    k.tick(it)
    assert c.ratio(METRIC_LLM_FALLBACK_RATE) == 0.0
