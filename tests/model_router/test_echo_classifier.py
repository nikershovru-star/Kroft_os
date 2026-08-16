"""ТЗ-ECHO E3 — LLM classifier tests (unit + integration-with-fallback).

Covers: IClassifier contract, LLMClassifier parsing/caching/fallback, RuleBasedRouter
classifier-first-then-policy priority, manual_overrides in YAML, and a real phi3:mini
integration test that is SKIPPED when the model is not reachable (so CI stays green
without Ollama). Mirrors the E1/E2 mock style (no live network forced).
"""

import os

import pytest

from contracts.i_classifier import IClassifier
from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_model_router import IModelRouter, ProviderSpec
from contracts.i_router_policy import IRouterPolicy
from services.model_router.classifier import LLMClassifier
from services.model_router.rule_based_router import RuleBasedRouter
from services.model_router.yaml_policy import YamlRouterPolicy


class FakeLLM(ILlm):
    """Returns a fixed answer (or raises) to simulate the classifier model."""

    def __init__(self, answer="analytical", fail=None):
        self.answer = answer
        self.fail = fail
        self.calls = 0

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls += 1
        if self.fail == "error":
            from contracts.i_llm_advisor import LLMError
            raise LLMError("boom")
        if self.fail == "timeout":
            from contracts.i_llm_advisor import LLMTimeout
            raise LLMTimeout("slow")
        return LlmResponse(text=self.answer, provider="phi3:mini")

    def stream(self, query: ModelQuery):
        yield self.complete(query)


class FakeRouter(IModelRouter):
    def __init__(self, clients):
        self._clients = clients
        self._specs = [ProviderSpec(name=getattr(c, "provider", f"m{i}")) for i, c in enumerate(clients)]

    def complete(self, query: ModelQuery) -> LlmResponse:
        return self._clients[0].complete(query) if self._clients else LlmResponse(text="")

    def stream(self, query: ModelQuery):
        yield self.complete(query)

    def providers(self):
        return list(self._specs)

    def client_for(self, name):
        for s, c in zip(self._specs, self._clients):
            if s.name == name:
                return c
        return None

    def route(self, query):
        return self._clients[0] if self._clients else None


# --- IClassifier contract ---
def test_iclassifier_is_abstract():
    with pytest.raises(TypeError):
        IClassifier()


def test_llmclassifier_returns_valid_category():
    c = LLMClassifier(FakeLLM(answer="analytical"))
    assert c.classify(ModelQuery(prompt="compare A vs B")) == "analytical"


def test_llmclassifier_lowercases_and_parses_preamble():
    c = LLMClassifier(FakeLLM(answer="Creative. Sure!"))
    assert c.classify(ModelQuery(prompt="write a poem")) == "creative"


def test_llmclassifier_invalid_answer_falls_back_to_none():
    c = LLMClassifier(FakeLLM(answer="I think it is code maybe"))
    # "i" is not a category -> returns None (router falls back to rule-based)
    assert c.classify(ModelQuery(prompt="x")) is None


def test_llmclassifier_error_returns_none():
    c = LLMClassifier(FakeLLM(fail="error"))
    assert c.classify(ModelQuery(prompt="analyze this")) is None


def test_llmclassifier_timeout_returns_none():
    c = LLMClassifier(FakeLLM(fail="timeout"))
    assert c.classify(ModelQuery(prompt="analyze this")) is None


def test_llmclassifier_caches():
    llm = FakeLLM(answer="factual")
    c = LLMClassifier(llm)
    q = ModelQuery(prompt="what is recursion")
    assert c.classify(q) == "factual"
    assert c.classify(q) == "factual"
    assert llm.calls == 1  # second call served from cache


def test_llmclassifier_empty_prompt_returns_none():
    c = LLMClassifier(FakeLLM(answer="code"))
    assert c.classify(ModelQuery(prompt="")) is None
    assert c.classify(ModelQuery(prompt="   ")) is None


# --- RuleBasedRouter classifier-first priority ---
def test_router_uses_classifier_before_policy():
    policy = YamlRouterPolicy.load_default()
    llm = FakeLLM(answer="creative")  # classifier says creative
    router = RuleBasedRouter(policy, FakeRouter([llm]), classifier=LLMClassifier(llm))
    # prompt has no creative keywords but classifier forces creative
    res = router.route(__import__("services.model_router.dtos", fromlist=["RouterRequest"]).RouterRequest(
        ModelQuery(prompt="calculate 2+2")))
    assert res.category == "creative"


def test_router_falls_back_to_policy_when_classifier_none():
    policy = YamlRouterPolicy.load_default()
    llm = FakeLLM(fail="error")  # classifier unavailable -> None
    router = RuleBasedRouter(policy, FakeRouter([llm]), classifier=LLMClassifier(llm))
    res = router.route(__import__("services.model_router.dtos", fromlist=["RouterRequest"]).RouterRequest(
        ModelQuery(prompt="write a python function to sort")))
    # policy rule-based: "python" -> code
    assert res.category == "code"


def test_router_no_classifier_uses_policy():
    policy = YamlRouterPolicy.load_default()
    llm = FakeLLM(answer="creative")  # would say creative, but no classifier passed
    router = RuleBasedRouter(policy, FakeRouter([llm]))
    res = router.route(__import__("services.model_router.dtos", fromlist=["RouterRequest"]).RouterRequest(
        ModelQuery(prompt="analyze and compare trade-offs")))
    assert res.category == "analytical"  # policy keyword wins


# --- manual_overrides in YAML ---
def test_manual_override_before_keywords():
    policy = YamlRouterPolicy.load_default()
    # "debug this crash" is pinned to code via manual_overrides, even with no code keywords
    assert policy.classify(ModelQuery(prompt="please debug this crash for me")) == "code"
    # "translate to" pinned to creative
    assert policy.classify(ModelQuery(prompt="translate to french")) == "creative"


# --- integration: real phi3:mini if reachable (skipped otherwise) ---
@pytest.mark.skipif(
    not os.environ.get("KROFT_RUN_INTEGRATION"),
    reason="set KROFT_RUN_INTEGRATION=1 with a reachable phi3:mini to run live classifier",
)
def test_llmclassifier_real_phi3():
    from composition.llm_client_factory import build_llm_client
    client = build_llm_client(model="phi3:mini")
    c = LLMClassifier(client)
    out = c.classify(ModelQuery(prompt="write a function to sort a list"))
    assert out in IRouterPolicy.CATEGORIES
