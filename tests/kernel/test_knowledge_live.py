"""Wave 8 (ADR-011) Phase F — LIVE golden test (gated).

Runs a real document through a REAL Router backed by OmniRoute / Ollama.
Skipped unless KNOWLEDGE_LIVE=1 — CI and normal runs stay offline.

    KNOWLEDGE_LIVE=1 pytest tests/test_knowledge_live.py -v

Env knobs:
    KNOWLEDGE_LIVE_BASE_URL  (default http://localhost:20128/v1  — OmniRoute)
    KNOWLEDGE_LIVE_MODEL     (default auto-select from the registry)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

LIVE = os.getenv("KNOWLEDGE_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set KNOWLEDGE_LIVE=1 to run live extraction")

DOC = (
    "Rust is a systems programming language created by Graydon Hoare.\n\n"
    "Its ownership model prevents data races at compile time."
)


@pytest.fixture()
def live_platform():
    from contracts.i_llm import ModelInfo
    from contracts.model_registry import ModelRegistry
    from infrastructure.graph_builder import InMemoryGraphBuilder
    from policies.budget_policy import BudgetPolicy
    from policies.privacy_policy import PrivacyPolicy
    from policies.provider_selection_policy import ProviderSelectionPolicy
    from services.policy_engine import PolicyEngine
    from adapters.router import Router
    from adapters.graph_knowledge_store import GraphKnowledgeStore
    from adapters.llm_entity_extractor import LLMEntityExtractor
    from services.knowledge_platform import HeuristicValidator, KnowledgePlatform

    base_url = os.getenv("KNOWLEDGE_LIVE_BASE_URL", "http://localhost:20128/v1")
    model_id = os.getenv("KNOWLEDGE_LIVE_MODEL", "")

    try:
        from adapters.omni_route_adapter import OmniRouteAdapter
        llm = OmniRouteAdapter(base_url=base_url)
    except Exception as exc:  # pragma: no cover - live only
        pytest.skip(f"OmniRoute adapter unavailable: {exc}")

    registry = ModelRegistry()
    try:
        registry.register_source(llm)
    except Exception as exc:  # pragma: no cover - live only
        pytest.skip(f"live gateway unreachable at {base_url}: {exc}")

    if model_id:
        registry.register_model(
            ModelInfo(id=model_id, provider="omniroute", reasoning=True, json_mode=True, free=True)
        )
    if not registry.catalog():
        pytest.skip(f"live catalog empty at {base_url}")

    engine = PolicyEngine(registry)
    engine.register(BudgetPolicy())
    engine.register(PrivacyPolicy())
    engine.register(ProviderSelectionPolicy(strategy="scored"))
    router = Router(engine, {"omniroute": llm})

    builder = InMemoryGraphBuilder()
    store = GraphKnowledgeStore(builder)
    platform = KnowledgePlatform(
        extractor=LLMEntityExtractor(router.route),
        validator=HeuristicValidator(min_confidence=0.5),
        graph=store,
        min_confidence=0.7,
    )
    return platform, store, builder


def test_live_document_produces_verified_facts(live_platform):
    platform, store, builder = live_platform
    report = platform.ingest(DOC, document_id="live-rust-doc")

    assert report.chunks == 2
    assert report.hypotheses > 0, f"live model produced no hypotheses: {report.audit_log}"

    facts = store.facts()
    assert facts, f"nothing cleared the confidence gate: {report.audit_log}"

    for f in facts:
        # Definition of Done (ADR-011 §2.5)
        assert f.subject and f.predicate and f.object
        assert f.source and f.source != "unknown"      # source=actual_model@doc
        assert "live-rust-doc" in f.source
        assert f.evidence
        assert 0.0 < f.confidence <= 1.0
        assert [h["action"] for h in f.history] == ["validated", "stored"]

    graph = builder.get_graph()
    assert graph["edges"], "graph received no edges"
    print(f"\nlive facts: {[(f.subject, f.predicate, f.object, f.source) for f in facts]}")
