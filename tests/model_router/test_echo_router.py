"""ТЗ-ECHO (E1) — unit + integration tests for the Echo-pattern router/ensemble layer.

Covers: ports (IRouterPolicy/IEnsembleOrchestrator contracts), YamlRouterPolicy rule
matching, RuleBasedRouter single + ensemble routing, SimpleEnsembleOrchestrator parallel
merge, and the run_kroft --router integration (OFF by default, no break of stock path).

Uses in-process fakes (no live model/network). K5: reuses contracts + existing adapters.
"""

from __future__ import annotations

import time
from typing import List, Optional

import pytest

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout
from contracts.i_model_router import IModelRouter, ProviderSpec
from contracts.i_router_policy import IRouterPolicy
from contracts.i_ensemble_orchestrator import (
    EnsembleResult,
    IEnsembleOrchestrator,
    MergeStrategy,
)

from services.model_router.dtos import RouterRequest, RouterResult
from services.model_router.ensemble_orchestrator import SimpleEnsembleOrchestrator
from services.model_router.yaml_policy import YamlRouterPolicy
from services.model_router.rule_based_router import RuleBasedRouter
from services.model_router.router_llm_adapter import RouterAsLlm
from services.model_router.classifier import LLMClassifier

POLICY = "config/router_policy.yaml"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeLLM(ILlm):
    """Configurable ILlm: returns a canned answer, or raises on demand."""

    def __init__(self, name: str, answer: str = "ok", fail: Optional[str] = None,
                 latency_ms: float = 1.0) -> None:
        self.provider = name
        self.model = f"model-{name}"
        self._answer = answer
        self._fail = fail
        self._latency = latency_ms
        self.calls = 0

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls += 1
        time.sleep(self._latency / 1000.0)
        if self._fail == "error":
            raise LLMError(f"{self.provider} boom")
        if self._fail == "timeout":
            raise LLMTimeout(f"{self.provider} slow")
        return LlmResponse(
            text=self._answer, provider=self.provider, model=self.model,
            actual_provider=self.provider, actual_model=self.model,
            tokens=10, tokens_out=10, latency_ms=self._latency, cost=0.0,
        )

    def stream(self, query: ModelQuery):
        raise NotImplementedError


class FakeRouter(IModelRouter):
    """Minimal IModelRouter that exposes the given clients as its providers."""

    def __init__(self, clients: List[ILlm], specs: List[ProviderSpec]) -> None:
        self._clients = clients
        self._specs = specs

    @property
    def providers(self) -> List[ProviderSpec]:
        return list(self._specs)

    def route(self, query: ModelQuery) -> Optional[ILlm]:
        return self._clients[0] if self._clients else None

    def client_for(self, name: str) -> Optional[ILlm]:
        for spec, client in zip(self._specs, self._clients):
            if spec.name == name:
                return client
        return None

    def complete(self, query: ModelQuery) -> LlmResponse:
        if not self._clients:
            raise LLMError("empty")
        return self._clients[0].complete(query)

    def stream(self, query: ModelQuery):
        raise NotImplementedError


# --------------------------------------------------------------------------
# Port contract tests
# --------------------------------------------------------------------------
def test_irouterpolicy_is_abstract():
    with pytest.raises(TypeError):
        IRouterPolicy()  # type: ignore[abstract]


def test_ensemble_orchestrator_is_abstract():
    with pytest.raises(TypeError):
        IEnsembleOrchestrator()  # type: ignore[abstract]


# --------------------------------------------------------------------------
# YamlRouterPolicy
# --------------------------------------------------------------------------
def test_yaml_policy_classify_keyword():
    p = YamlRouterPolicy.load_default()
    assert p.classify(ModelQuery(prompt="write a python function to sort")) == "code"
    assert p.classify(ModelQuery(prompt="compose a poem about the sea")) == "creative"
    assert p.classify(ModelQuery(prompt="what is the definition of entropy")) == "factual"
    assert p.classify(ModelQuery(prompt="analyze and compare the trade-offs")) == "analytical"


def test_yaml_policy_classify_default_fallback():
    p = YamlRouterPolicy.load_default()
    # no keyword matches -> default category
    assert p.classify(ModelQuery(prompt="hello there")) == p._default


def test_yaml_policy_providers_for():
    p = YamlRouterPolicy.load_default()
    specs = p.providers_for("code")
    names = [s.name for s in specs]
    assert names == ["local-ollama", "omni-route"]
    # priority follows list order (lower = first)
    assert specs[0].priority < specs[1].priority


def test_yaml_policy_categories():
    p = YamlRouterPolicy.load_default()
    cats = p.categories()
    assert set(cats) == {"code", "creative", "factual", "analytical"}


# --------------------------------------------------------------------------
# SimpleEnsembleOrchestrator
# --------------------------------------------------------------------------
def test_ensemble_single_client_delegates():
    e = SimpleEnsembleOrchestrator()
    c = FakeLLM("a", answer="only")
    res = e.run(ModelQuery(prompt="x"), [c])
    assert isinstance(res, EnsembleResult)
    assert res.response.text == "only"
    assert res.latency_ms >= 0
    assert not res.per_model or len(res.per_model) == 1


def test_ensemble_parallel_merge_best_confidence():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("a", answer="short", latency_ms=5)
    b = FakeLLM("b", answer="a much longer and more detailed answer here", latency_ms=5)
    res = e.run(ModelQuery(prompt="x"), [a, b], strategy=MergeStrategy.BEST_CONFIDENCE)
    # longer answer wins (proxy confidence)
    assert res.response.text == "a much longer and more detailed answer here"
    assert res.response.actual_provider == "b"
    assert set(res.per_model.keys()) == {"a", "b"}


def test_ensemble_all_fail_returns_error_not_raise():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("a", fail="error")
    b = FakeLLM("b", fail="timeout")
    res = e.run(ModelQuery(prompt="x"), [a, b])
    assert res.response.error is not None  # graceful, no raise


def test_ensemble_one_failure_excluded():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("a", fail="error")
    b = FakeLLM("b", answer="backup answer", latency_ms=2)
    res = e.run(ModelQuery(prompt="x"), [a, b])
    assert res.response.text == "backup answer"
    assert res.response.error is None


def test_ensemble_empty_clients():
    e = SimpleEnsembleOrchestrator()
    res = e.run(ModelQuery(prompt="x"), [])
    assert res.response.error is not None


# --------------------------------------------------------------------------
# RuleBasedRouter
# --------------------------------------------------------------------------
def _router_with(clients, specs) -> RuleBasedRouter:
    policy = YamlRouterPolicy.load_default()
    rtr = FakeRouter(clients, specs)
    return RuleBasedRouter(policy, rtr)


def test_rule_router_single_path_uses_first_provider():
    a = FakeLLM("local-ollama", answer="code-answer", latency_ms=2)
    r = _router_with([a], [ProviderSpec(name="local-ollama", base_url="http://local-ollama/v1", priority=0)])
    res = r.route(RouterRequest(query=ModelQuery(prompt="write a python function")))
    assert isinstance(res, RouterResult)
    assert res.response.text == "code-answer"
    assert res.category == "code"
    assert res.used_ensemble is False
    assert res.chosen_providers == ["local-ollama"]


def test_rule_router_ensemble_for_analytical_multi():
    a = FakeLLM("omni-route", answer="short", latency_ms=3)
    b = FakeLLM("local-ollama", answer="longer analytical synthesis answer", latency_ms=3)
    r = _router_with(
        [a, b],
        [ProviderSpec(name="omni-route", base_url="http://omni-route/v1", priority=0), ProviderSpec(name="local-ollama", base_url="http://local-ollama/v1", priority=1)],
    )
    res = r.route(RouterRequest(query=ModelQuery(prompt="analyze and compare the trade-offs")))
    assert res.used_ensemble is True
    assert res.response.text == "longer analytical synthesis answer"
    assert set(res.chosen_providers) == {"omni-route", "local-ollama"}


def test_rule_router_no_provider_graceful():
    r = _router_with([], [])
    res = r.route(RouterRequest(query=ModelQuery(prompt="write code")))
    assert res.response.error is not None  # LLM-01 graceful, no crash


def test_rule_router_preclassified_category():
    a = FakeLLM("omni-route", answer="fact", latency_ms=2)
    r = _router_with([a], [ProviderSpec(name="omni-route", base_url="http://omni-route/v1", priority=0)])
    # bypass keyword classify by supplying category directly
    res = r.route(RouterRequest(query=ModelQuery(prompt="zzz"), category="factual"))
    assert res.category == "factual"
    assert res.response.text == "fact"


# --------------------------------------------------------------------------
# RouterAsLlm adapter (integration with ILlm contract)
# --------------------------------------------------------------------------
def test_router_as_llm_completes():
    a = FakeLLM("local-ollama", answer="via-router", latency_ms=2)
    r = _router_with([a], [ProviderSpec(name="local-ollama", base_url="http://local-ollama/v1", priority=0)])
    wrapped = RouterAsLlm(r)
    assert isinstance(wrapped, ILlm)
    resp = wrapped.complete(ModelQuery(prompt="write a python function"))
    assert resp.text == "via-router"
    # provider provenance is preserved (router does not erase the real provider)
    assert resp.provider == "local-ollama"


# --------------------------------------------------------------------------
# run_kroft --router integration (OFF by default)
# --------------------------------------------------------------------------
def test_run_kroft_router_flag_off_is_default():
    from composition.run_kroft import _parse_args
    cfg = _parse_args(["--llm", "none"])
    assert cfg.router is False  # default OFF -> stock path untouched


def test_run_kroft_router_flag_parses():
    from composition.run_kroft import _parse_args
    cfg = _parse_args(["--router"])
    assert cfg.router is True


# -------------------------------------------------------------------------
# E3 classifier config (ТЗ 2.4): router_policy.yaml `classifier:` section
# -------------------------------------------------------------------------
def test_yaml_policy_exposes_classifier_config():
    p = YamlRouterPolicy.load_default()
    cls = p.classifier_config()
    assert cls.get("enabled") is True
    assert cls.get("model") == "phi3:mini"
    assert cls.get("timeout") == 5
    assert cls.get("fallback") == "rule_based"


def test_yaml_policy_classifier_config_absent_returns_empty():
    import tempfile, os
    from services.model_router.yaml_policy import YamlRouterPolicy
    raw = "default: factual\npriority: [factual]\ncategories:\n  factual:\n    keywords: [what]\n    providers: [local-ollama]\n"
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(raw)
    try:
        p = YamlRouterPolicy(path)
        assert p.classifier_config() == {}
    finally:
        os.remove(path)


def test_llmclassifier_accepts_config_timeout():
    c = LLMClassifier(FakeLLM("phi3", answer="factual"), model="phi3:mini", timeout=5.0)
    assert c._timeout == 5.0
    assert c.classify(ModelQuery(prompt="")) is None
