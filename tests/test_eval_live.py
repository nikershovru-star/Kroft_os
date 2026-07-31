"""Wave 7 (ADR-010) — LIVE golden test (gated).

Runs the real Golden Dataset through the real Router against OmniRoute
(default :20128) and/or Ollama (:11434). Skipped unless OMNIROUTE_LIVE=1
(resp. OLLAMA_LIVE=1) — never fails in CI/offline (Roadmap Phase F).

Requires the concrete adapters (adapters.omni_route_adapter / ollama_adapter)
which are NOT imported at module top-level so the suite stays importable offline.
"""
import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _live_router():
    from contracts.i_llm import ModelQuery
    from contracts.model_registry import ModelRegistry
    from policies.budget_policy import BudgetPolicy
    from policies.provider_selection_policy import ProviderSelectionPolicy
    from services.policy_engine import PolicyEngine
    from adapters.router import Router
    from adapters.omni_route_adapter import OmniRouteAdapter
    from adapters.ollama_adapter import OllamaAdapter

    reg = ModelRegistry()
    reg.register_source(OmniRouteAdapter())
    reg.register_source(OllamaAdapter())
    eng = PolicyEngine(reg)
    eng.register(BudgetPolicy(per_call_limit=0.5))
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    adapters = {
        "omniroute": OmniRouteAdapter(),
        "ollama": OllamaAdapter(),
    }
    return lambda q: Router(eng, adapters).route(q)


@pytest.mark.skipif(os.environ.get("OMNIROUTE_LIVE") != "1",
                    reason="set OMNIROUTE_LIVE=1 to run live golden eval")
def test_live_golden_dataset_eval():
    from contracts.i_llm import ModelQuery
    from services.evaluation_platform import MetricsCollector, BenchmarkRunner, InMemoryScorecard
    from services.golden_dataset import fetch_dataset

    router = _live_router()
    store = InMemoryScorecard()
    runner = BenchmarkRunner(MetricsCollector(), store)
    for task in fetch_dataset():
        sc = runner.run(task, lambda q: router(ModelQuery(prompt=task.input, reasoning=(task.category == "reasoning"))))
        assert sc.model_id, f"no model selected for {task.id}"
    # at least the QA task should resolve to a real model with a recorded scorecard
    assert store.fetch("qa-001", sc.model_id) is not None
