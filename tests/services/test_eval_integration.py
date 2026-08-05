"""Wave 7 (ADR-010) — integration: Router + Registry + Policy + Evaluation.

Offline (mock adapters). Demonstrates the full loop:
  Golden Dataset -> BenchmarkRunner -> Router -> Scorecard
  -> ProviderSelectionPolicy v2 blends measured accuracy.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.model_registry import ModelRegistry
from contracts.i_eval import IScorecard, Task, TaskCategory
from policies.budget_policy import BudgetPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from policies.privacy_policy import PrivacyPolicy
from services.policy_engine import PolicyEngine
from adapters.router import Router
from services.evaluation_platform import (
    MetricsCollector,
    BenchmarkRunner,
    InMemoryScorecard,
)
from services.golden_dataset import fetch_dataset


class _MockLLM(ILlm):
    """Deterministic mock: answers from a fixed map; fails on demand."""
    def __init__(self, answers, fail=None):
        self.answers = answers
        self.fail = set(fail or [])
        self.last_query = None

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.last_query = query
        if query.preferred_provider in self.fail:
            return LlmResponse(text="", error=f"boom:{query.preferred_provider}")
        ans = self.answers.get(query.preferred_provider, "no-answer")
        return LlmResponse(text=ans, model=query.preferred_provider,
                          actual_model=query.preferred_provider, latency_ms=100.0, cost=0.0,
                          trace_id="trace-1")

    def stream(self, query):
        yield self.complete(query).text


def _registry():
    r = ModelRegistry()
    r.register_model(ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False,
                               context_window=128000, free=False, cost_per_1k=5.0))
    r.register_model(ModelInfo(id="qwen", provider="ollama", reasoning=False, local=True,
                               context_window=32000, free=True, cost_per_1k=0.0))
    r.register_model(ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True,
                               context_window=16000, free=True, cost_per_1k=0.0))
    return r


def _router():
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(PrivacyPolicy())            # no restrictions by default
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    adapters = {"omniroute": _MockLLM({"gpt": "Paris"}), "ollama": _MockLLM({"qwen": "Paris", "phi4": "Yes"})}
    return Router(eng, adapters)


def test_eval_runs_full_stack_offline():
    router = _router()
    store = InMemoryScorecard()
    runner = BenchmarkRunner(MetricsCollector(), store)
    ds = fetch_dataset()
    # qa-001 expects "Paris" -> both providers answer correctly (router picks the model)
    qa = next(t for t in ds if t.id == "qa-001")
    sc_gpt = runner.run(qa, lambda q: router.route(ModelQuery(prompt=qa.input, reasoning=False)))
    assert sc_gpt.model_id in ("gpt", "qwen", "phi4")
    assert sc_gpt.metrics["accuracy"] == 1.0
    sc_qwen = runner.run(qa, lambda q: router.route(ModelQuery(prompt=qa.input, reasoning=False, local=True)))
    assert sc_qwen.model_id in ("qwen", "phi4")
    assert sc_qwen.metrics["accuracy"] == 1.0
    assert store.leaderboard(sc_gpt.model_id) == 1.0


def test_provider_selection_v2_blends_scorecard():
    store = InMemoryScorecard()
    # seed: gpt measured worse than qwen on the golden set
    store.record(__import__("services.evaluation_platform", fromlist=["Scorecard"]).Scorecard(
        task_id="qa-001", model_id="gpt", output="x", metrics={"accuracy": 0.2}))
    store.record(__import__("services.evaluation_platform", fromlist=["Scorecard"]).Scorecard(
        task_id="qa-001", model_id="qwen", output="x", metrics={"accuracy": 1.0}))
    # engine with v2 policy (scorecard blend)
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(PrivacyPolicy())
    eng.register(ProviderSelectionPolicy(strategy="scored", scorecard=store, accuracy_weight=0.9))
    ctx = PolicyContext(query=ModelQuery(prompt="capital of France?", reasoning=False))
    d = eng.decide(ctx)
    # with high accuracy_weight, the measured-better qwen must outrank gpt
    assert d.selected_model.id == "qwen", d.selected_model.id
    assert "acc=" in d.audit_log[0]


def test_provider_selection_v2_without_scorecard_unchanged():
    # no scorecard -> pure heuristic, must not crash and must still pick a model
    eng = PolicyEngine(_registry())
    eng.register(BudgetPolicy())
    eng.register(PrivacyPolicy())
    eng.register(ProviderSelectionPolicy(strategy="scored"))  # scorecard=None (default)
    ctx = PolicyContext(query=ModelQuery(prompt="hi", reasoning=False))
    d = eng.decide(ctx)
    assert d.allowed
    assert d.selected_model is not None
