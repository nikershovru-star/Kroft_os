"""Wave 5 (ADR-009) policy engine tests — mocks, no network (Phase E)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.model_registry import ModelRegistry
from policies.budget_policy import BudgetPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine, FallbackPolicy


class _FakeLLM(ILlm):
    """Mock adapter: returns ok unless its model id is in ._fail set."""
    def __init__(self, answer="ok"):
        self.answer = answer
        self._fail = set()
        self.last_query = None

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.last_query = query
        if query.preferred_provider in self._fail:
            return LlmResponse(text="", error=f"boom:{query.preferred_provider}")
        return LlmResponse(text=self.answer, model=query.preferred_provider, actual_model=query.preferred_provider)

    def stream(self, query):
        yield self.complete(query).text


def _registry():
    r = ModelRegistry()
    r.register_model(ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False, context_window=128000, free=False, cost_per_1k=5.0))
    r.register_model(ModelInfo(id="qwen", provider="ollama", reasoning=False, local=True, context_window=32000, free=True, cost_per_1k=0.0))
    r.register_model(ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True, context_window=16000, free=True, cost_per_1k=0.0))
    return r


def test_budget_veto_per_call():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy(per_call_limit=0.5))
    eng.register(ProviderSelectionPolicy())
    # expensive model, long prompt -> estimated cost > 0.5
    q = ModelQuery(prompt="x" * 4000, reasoning=True)
    ctx = PolicyContext(query=q, estimated_cost=2.5)
    d = eng.decide(ctx)
    assert not d.allowed, d.reason
    assert d.vetoed_by == "BudgetPolicy", d.vetoed_by


def test_provider_selection_local_pref():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())  # no limits
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    q = ModelQuery(prompt="hi", reasoning=True, local=True)
    ctx = PolicyContext(query=q)
    d = eng.decide(ctx)
    assert d.allowed
    assert d.selected_model.local is True, d.selected_model.id
    assert len(d.fallback_chain) >= 1


def test_pipeline_ranking_selects_reasoning():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    q = ModelQuery(prompt="reason please", reasoning=True, local=False)
    ctx = PolicyContext(query=q, estimated_cost=0.0)
    d = eng.decide(ctx)
    assert d.allowed
    # chosen model must satisfy the reasoning requirement of the query
    assert d.selected_model.reasoning is True, d.selected_model.id
    assert len(d.fallback_chain) >= 1


def test_execute_primary_ok():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(ProviderSelectionPolicy())
    llm = _FakeLLM("answer")
    resp = eng.execute(ModelQuery(prompt="hi", reasoning=True), llm)
    assert resp.ok()
    assert resp.text == "answer"


def test_execute_fallback_on_failure():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(ProviderSelectionPolicy(strategy="scored"))  # phi4 (local reasoning) first
    llm = _FakeLLM("fallback-answer")
    llm._fail = {"phi4"}  # primary (selected) fails -> fallback to next in chain
    resp = eng.execute(ModelQuery(prompt="hi", reasoning=True), llm)
    assert resp.ok(), resp.error
    assert resp.text == "fallback-answer"
    # the call that succeeded must NOT be the failed one
    assert llm.last_query.preferred_provider != "phi4"


def test_fallback_policy_should_retry():
    fb = FallbackPolicy()
    assert fb.should_retry(Exception("429 rate limit")) is True
    assert fb.should_retry(Exception("503 unavailable")) is True
    assert fb.should_retry(Exception("401 unauthorized")) is False
