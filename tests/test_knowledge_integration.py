"""Wave 8 (ADR-011) Phase E — integration: real Router + PolicyEngine + real
InMemoryGraphBuilder + mock ILlm adapter.

Proves the ADR-011 §2.2 chain end to end, offline:
    Router -> LLM -> Hypothesis -> Evaluation -> Fact -> Graph
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from contracts.i_eval import Scorecard, Task, TaskCategory
from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.model_registry import ModelRegistry
from infrastructure.graph_builder import InMemoryGraphBuilder
from policies.budget_policy import BudgetPolicy
from policies.privacy_policy import PrivacyPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from services.evaluation_platform import (
    BenchmarkRunner,
    InMemoryScorecard,
    MetricsCollector,
)
from adapters.router import Router
from adapters.graph_knowledge_store import GraphKnowledgeStore
from adapters.llm_entity_extractor import LLMEntityExtractor
from services.knowledge_platform import HeuristicValidator, KnowledgePlatform

DOC = (
    "Rust is a systems language.\n\n"
    "Ownership prevents data races."
)

TRIPLES = json.dumps(
    [
        {"subject": "Rust", "predicate": "is", "object": "systems language"},
        {"subject": "Ownership", "predicate": "prevents", "object": "data races"},
    ]
)


class _MockLLM(ILlm):
    """Deterministic extraction model. Never pass ok= (it is a method)."""

    def __init__(self, payload=TRIPLES):
        self.payload = payload
        self.seen = []

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.seen.append(query)
        return LlmResponse(
            text=self.payload,
            model=query.preferred_provider or "mock",
            actual_model=query.preferred_provider or "mock",
            provider="mock",
            trace_id="trace-int",
            latency_ms=12.0,
            cost=0.0,
        )

    def stream(self, query):
        yield self.complete(query).text


def _registry() -> ModelRegistry:
    r = ModelRegistry()
    r.register_model(ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False,
                               context_window=128000, free=False, cost_per_1k=5.0))
    r.register_model(ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True,
                               context_window=16000, free=True, cost_per_1k=0.0))
    r.register_model(ModelInfo(id="qwen", provider="ollama", reasoning=False, local=True,
                               context_window=32000, free=True, cost_per_1k=0.0))
    return r


def _router_and_llm():
    engine = PolicyEngine(_registry())
    engine.register(BudgetPolicy())
    engine.register(PrivacyPolicy())
    engine.register(ProviderSelectionPolicy(strategy="scored"))
    llm = _MockLLM()
    router = Router(engine, {"omniroute": llm, "ollama": llm})
    return router, llm


def _platform(scorer=None, min_confidence=0.7):
    router, llm = _router_and_llm()
    builder = InMemoryGraphBuilder()
    store = GraphKnowledgeStore(builder)
    platform = KnowledgePlatform(
        extractor=LLMEntityExtractor(router.route),
        validator=HeuristicValidator(min_confidence=0.5),
        graph=store,
        scorer=scorer,
        min_confidence=min_confidence,
    )
    return platform, store, builder, llm


def test_full_chain_router_llm_hypothesis_fact_graph():
    platform, store, builder, llm = _platform()
    report = platform.ingest(DOC, document_id="rust-doc")

    assert report.chunks == 2
    assert report.hypotheses == 4
    assert llm.seen, "router never reached the LLM adapter"

    facts = store.facts()
    assert len(facts) == 2
    # Definition of Done: source / evidence / confidence / history on every edge
    for f in facts:
        assert f.source and "rust-doc" in f.source
        assert f.evidence
        assert 0.0 < f.confidence <= 1.0
        assert [h["action"] for h in f.history] == ["validated", "stored"]

    graph = builder.get_graph()
    relations = {e["relation"] for e in graph["edges"]}
    assert {"is", "prevents"} <= relations
    assert "Rust" in {n["id"] for n in graph["nodes"]}


def test_policy_engine_picks_reasoning_model_for_extraction():
    platform, _, _, llm = _platform()
    platform.ingest("Rust is a systems language.", document_id="d")
    registry = _registry()
    chosen = {q.preferred_provider for q in llm.seen}
    # extraction asked for reasoning=True -> only reasoning-capable models allowed
    for model_id in chosen:
        info = registry.capabilities(model_id)
        assert info is not None, model_id
        assert info.reasoning is True, f"{model_id} is not reasoning-capable"


def test_evaluation_confidence_gates_the_graph():
    """Same document, two Evaluation verdicts -> opposite graph outcomes."""
    low = Scorecard(task_id="k", model_id="m", output="", metrics={"accuracy": 0.4},
                    evidence="acc=0.40")
    high = Scorecard(task_id="k", model_id="m", output="", metrics={"accuracy": 0.92},
                     evidence="acc=0.92")

    p_low, s_low, _, _ = _platform(scorer=lambda h: low)
    p_low.ingest(DOC, document_id="d")
    assert s_low.facts() == []

    p_high, s_high, _, _ = _platform(scorer=lambda h: high)
    p_high.ingest(DOC, document_id="d")
    assert len(s_high.facts()) == 2
    assert all(f.confidence == 0.92 for f in s_high.facts())
    assert all("acc=0.92" in f.evidence for f in s_high.facts())


def test_scorer_backed_by_real_benchmark_runner():
    """Evaluation Platform (Wave 7) really produces the confidence (LAW 5)."""
    router, _ = _router_and_llm()
    store_sc = InMemoryScorecard()
    runner = BenchmarkRunner(MetricsCollector(), store_sc)

    def scorer(hypothesis):
        task = Task(
            id=f"kn-{hypothesis.subject}",
            category=TaskCategory.ENTITY_EXTRACTION,
            input=hypothesis.evidence or hypothesis.subject,
            expected=TRIPLES,          # mock LLM echoes exactly this payload
        )
        return runner.run(task, lambda q: router.route(ModelQuery(prompt=task.input, reasoning=True)))

    builder = InMemoryGraphBuilder()
    store = GraphKnowledgeStore(builder)
    platform = KnowledgePlatform(
        extractor=LLMEntityExtractor(router.route),
        validator=HeuristicValidator(min_confidence=0.5),
        graph=store,
        scorer=scorer,
        min_confidence=0.7,
    )
    platform.ingest("Rust is a systems language.", document_id="eval-doc")

    facts = store.facts()
    assert facts, "measured accuracy 1.0 should clear the 0.7 threshold"
    assert all(f.confidence == 1.0 for f in facts)
    assert store_sc.leaderboard(facts[0].source.split("@")[0]) >= 0.0


def test_services_layer_has_no_adapter_imports():
    """LAW 2 guard, scoped to the Wave 8 service module."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "services" / "knowledge_platform.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
    assert "adapters" not in imported
    assert "infrastructure" not in imported
    assert "services" not in imported
