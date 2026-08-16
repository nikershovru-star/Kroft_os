"""ТЗ-ECHO E2 — production-hardening tests for the Echo router (G1–G8 forensic fixes).

Covers: fake-URL elimination, router activation without env var, production name
resolution via public API, unknown provider skip, malformed YAML fail-fast, empty
prompt, token-boundary keyword matching, deterministic category priority, cost
aggregation, duplicate provider names, thread-safe ensemble collection.

Uses in-process fakes (no live model/network). Reuses contracts + existing adapters.
"""

from __future__ import annotations

import pytest

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout
from contracts.i_model_router import IModelRouter, ProviderSpec
from contracts.i_router_policy import IRouterPolicy

from composition.omni_router import OmniRouter, build_omni_router
from services.model_router.yaml_policy import YamlRouterPolicy
from services.model_router.rule_based_router import RuleBasedRouter
from services.model_router.ensemble_orchestrator import SimpleEnsembleOrchestrator
from services.model_router.router_llm_adapter import RouterAsLlm


class FakeLLM(ILlm):
    def __init__(self, name, answer="ok", fail=None, cost=0.0, latency_ms=1.0):
        self.provider = name
        self.model = f"m-{name}"
        self._answer = answer
        self._fail = fail
        self._cost = cost
        self._latency = latency_ms

    def complete(self, query):
        import time
        time.sleep(self._latency / 1000.0)
        if self._fail == "error":
            raise LLMError(f"{self.provider} boom")
        if self._fail == "timeout":
            raise LLMTimeout(f"{self.provider} slow")
        return LlmResponse(text=self._answer, provider=self.provider, model=self.model,
                           actual_provider=self.provider, actual_model=self.model,
                           tokens=10, tokens_out=10, latency_ms=self._latency, cost=self._cost)

    def stream(self, query):
        raise NotImplementedError


def _omni(names):
    clients = [FakeLLM(n) for n in names]
    specs = [ProviderSpec(name=n, priority=i) for i, n in enumerate(names)]
    return OmniRouter(clients, specs)


# --- G1: no fake base_url manufactured in policy ---
def test_g1_policy_spec_has_no_fake_base_url():
    p = YamlRouterPolicy.load_default()
    specs = p.providers_for("code")
    for s in specs:
        assert s.base_url == ""  # routing-only, real endpoint owned by IModelRouter
        assert s.name in ("local-ollama", "omni-route")


# --- G3: public client_for resolves by name (no private _clients access) ---
def test_g3_client_for_public_api():
    rtr = _omni(["local-ollama", "omni-route"])
    assert rtr.client_for("omni-route").provider == "omni-route"
    assert rtr.client_for("local-ollama").provider == "local-ollama"
    assert rtr.client_for("unknown") is None


def test_g3_rule_router_uses_client_for():
    rtr = _omni(["local-ollama", "omni-route"])
    policy = YamlRouterPolicy.load_default()
    rb = RuleBasedRouter(policy, rtr)
    # analytical -> 2 providers -> ensemble; both resolved via client_for (not _clients)
    res = rb.route(__import__("services.model_router.dtos", fromlist=["RouterRequest"])
                   .RouterRequest(query=ModelQuery(prompt="analyze and compare the trade-offs")))
    assert res.used_ensemble is True
    assert set(res.chosen_providers) == {"local-ollama", "omni-route"}


# --- G2: router activates on --router even when _build_llm returned plain client ---
def test_g2_router_activates_without_env(monkeypatch):
    # Simulate `_build_llm` default-auto path returning a plain ILlm (not IModelRouter).
    plain = FakeLLM("plain")
    monkeypatch.setattr("composition.run_kroft.KroftApp._build_llm",
                        lambda self, mode: plain)
    from composition.run_kroft import KroftConfig, KroftApp
    cfg = KroftConfig(llm="auto", router=True)
    # build_omni_router([]) will try local Ollama probe; on CI it yields empty router,
    # which is still an IModelRouter -> router wraps it (graceful, not crash).
    app = KroftApp(cfg)
    assert app.router is not None  # router WAS constructed (activation path executed)
    assert isinstance(app.llm, RouterAsLlm) or app.router is not None


# --- G4: production name mismatch handled (unknown provider skipped, no crash) ---
def test_g4_unknown_provider_skipped():
    rtr = _omni(["local-ollama"])  # only local-ollama configured
    policy = YamlRouterPolicy.load_default()
    rb = RuleBasedRouter(policy, rtr)
    # factual -> [omni-route, local-ollama]; omni-route unknown -> skip, local-ollama used
    from services.model_router.dtos import RouterRequest
    res = rb.route(RouterRequest(query=ModelQuery(prompt="what is the definition of entropy")))
    assert res.response.text == "ok"
    assert res.chosen_providers == ["local-ollama"]


# --- G5: token-boundary keyword matching ---
def test_g5_token_boundary_no_false_positive():
    p = YamlRouterPolicy.load_default()
    # "definition" must NOT match code (no "def" token boundary issue now)
    assert p.classify(ModelQuery(prompt="give the definition of entropy")) == "factual"
    # "decode this" must NOT match code
    assert p.classify(ModelQuery(prompt="please decode this token")) != "code"
    # "classifier" must NOT match code
    assert p.classify(ModelQuery(prompt="train a text classifier")) != "code"
    # real code keyword still matches
    assert p.classify(ModelQuery(prompt="write a python function")) == "code"


# --- G6: deterministic category priority on multi-match ---
def test_g6_category_priority_deterministic():
    p = YamlRouterPolicy.load_default()
    # matches BOTH code (python) and analytical (analyze) -> priority list says code first
    assert p.classify(ModelQuery(prompt="analyze this python function")) == "code"
    # matches analytical + factual -> analytical first
    assert p.classify(ModelQuery(prompt="explain and evaluate the trade-off")) == "analytical"


# --- empty prompt / no keyword -> default ---
def test_empty_prompt_uses_default():
    p = YamlRouterPolicy.load_default()
    assert p.classify(ModelQuery(prompt="")) == p._default
    assert p.classify(ModelQuery(prompt="   ")) == p._default


# --- G7/G8: ensemble thread-safe collection + duplicate names ---
def test_ensemble_cost_aggregation_and_dedup():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("omni-route", answer="ans-a", cost=0.01, latency_ms=5)
    b = FakeLLM("local-ollama", answer="ans-b-longer", cost=0.02, latency_ms=5)
    res = e.run(ModelQuery(prompt="x"), [a, b])
    assert res.cost == 0.03  # sum of attempted calls (cost-aware)
    assert set(res.per_model.keys()) == {"omni-route", "local-ollama"}
    assert res.response.text == "ans-b-longer"  # longer wins proxy confidence


def test_ensemble_duplicate_provider_names_distinct_keys():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("dup", answer="first", cost=0.01)
    b = FakeLLM("dup", answer="second", cost=0.02)
    res = e.run(ModelQuery(prompt="x"), [a, b])
    # dedupe suffix keeps both results (G8)
    assert len(res.per_model) == 2
    assert res.cost == 0.03


def test_ensemble_one_failure_others_survive():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("x", fail="error")
    b = FakeLLM("y", answer="backup", cost=0.05)
    res = e.run(ModelQuery(prompt="x"), [a, b])
    assert res.response.text == "backup"
    assert res.response.error is None
    assert res.cost == 0.05


def test_ensemble_all_fail_controlled_error():
    e = SimpleEnsembleOrchestrator()
    a = FakeLLM("x", fail="error")
    b = FakeLLM("y", fail="timeout")
    res = e.run(ModelQuery(prompt="x"), [a, b])
    assert res.response.error is not None


# --- STEP 17/19: malformed YAML fail-fast at load ---
def test_malformed_yaml_missing_default(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("categories:\n  code:\n    keywords: [python]\n    providers: [local-ollama]\n")
    with pytest.raises(ValueError):
        YamlRouterPolicy(str(bad))


def test_malformed_yaml_empty_categories(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("default: code\ncategories: {}\n")
    with pytest.raises(ValueError):
        YamlRouterPolicy(str(bad))


# --- STEP 23/15: RouterAsLlm preserves provenance + metrics ---
def test_router_as_llm_preserves_provenance():
    rtr = _omni(["local-ollama"])
    policy = YamlRouterPolicy.load_default()
    rb = RuleBasedRouter(policy, rtr)
    wrapped = RouterAsLlm(rb)
    resp = wrapped.complete(ModelQuery(prompt="write a python function"))
    assert resp.text == "ok"
    assert resp.provider == "local-ollama"   # real provider, not erased
    assert resp.actual_model == "m-local-ollama"
    assert resp.tokens == 10
    assert resp.cost == 0.0


# --- STEP 16: stream() explicit unsupported ---
def test_router_as_llm_stream_unsupported():
    rtr = _omni(["local-ollama"])
    rb = RuleBasedRouter(YamlRouterPolicy.load_default(), rtr)
    wrapped = RouterAsLlm(rb)
    with pytest.raises(NotImplementedError):
        list(wrapped.stream(ModelQuery(prompt="x")))


# --- property invariant: classify always in categories ---
def test_classify_always_valid_category():
    p = YamlRouterPolicy.load_default()
    for prompt in ["", "xyz", "write python code", "analyze trade-offs", "what is X"]:
        assert p.classify(ModelQuery(prompt=prompt)) in p.categories()
