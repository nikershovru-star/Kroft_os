"""Wave 5 (ADR-009) integration golden tests — Phase G (no network).

Exercises the full stack: Router -> PolicyEngine -> policies -> ILlm adapter,
using mock adapters so it is deterministic and offline. Mirrors ADR-009 §11
golden: Budget veto + ProviderSelection local preference.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.model_registry import ModelRegistry
from policies.budget_policy import BudgetPolicy, estimate_cost
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from adapters.router import Router


class _Adapter(ILlm):
    def __init__(self, name, provider):
        self.name = name
        self.provider = provider
        self.calls = []

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls.append(query)
        return LlmResponse(text=f"ans-from-{self.name}", model=query.preferred_provider,
                          actual_model=query.preferred_provider)

    def stream(self, query):
        yield self.complete(query).text


def _build():
    reg = ModelRegistry()
    reg.register_model(ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False,
                                 context_window=128000, free=False, cost_per_1k=5.0))
    reg.register_model(ModelInfo(id="qwen", provider="ollama", reasoning=False, local=True,
                                 context_window=32000, free=True, cost_per_1k=0.0))
    reg.register_model(ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True,
                                 context_window=16000, free=True, cost_per_1k=0.0))
    eng = PolicyEngine(reg)
    eng.register(BudgetPolicy(per_call_limit=0.5))
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    adapters = {"omniroute": _Adapter("omni", "omniroute"), "ollama": _Adapter("ollama", "ollama")}
    router = Router(eng, adapters)
    return router, adapters


def test_golden_budget_veto():
    router, _ = _build()
    # expensive non-local reasoning -> estimated cost > per_call_limit
    resp = router.route(ModelQuery(prompt="x" * 4000, reasoning=True, local=False))
    assert not resp.ok(), "expected veto"
    assert "BudgetPolicy" in (resp.error or ""), resp.error


def test_golden_provider_selection_local():
    router, adapters = _build()
    resp = router.route(ModelQuery(prompt="hi", reasoning=False, local=True))
    assert resp.ok(), resp.error
    # selected must be a local ollama model, served by the ollama adapter
    assert adapters["ollama"].calls, "ollama adapter should have been used"
    assert "ans-from-ollama" == resp.text


def test_golden_estimate_cost_free_is_zero():
    m = ModelInfo(id="q", provider="ollama", local=True, free=True, cost_per_1k=0.0)
    assert estimate_cost(ModelQuery(prompt="x" * 4000), m) == 0.0
