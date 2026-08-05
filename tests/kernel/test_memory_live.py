"""Wave 9 (ADR-012) Phase G — LIVE golden test (gated).

A real two-turn dialogue through a REAL Router:
    turn 1: "Меня зовут Алиса"
    turn 2: "Как меня зовут?"  -> the model must answer "Алиса",
                                  and it can only know that from Session Memory.

Skipped unless MEMORY_LIVE=1.

    MEMORY_LIVE=1 pytest tests/test_memory_live.py -v

Env knobs:
    MEMORY_LIVE_BASE_URL  (default http://localhost:20128/v1 — OmniRoute)
    MEMORY_LIVE_MODEL     (optional explicit model id)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

LIVE = os.getenv("MEMORY_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set MEMORY_LIVE=1 to run the live dialogue")


@pytest.fixture()
def live_stack():
    from contracts.i_llm import ModelInfo
    from contracts.model_registry import ModelRegistry
    from policies.budget_policy import BudgetPolicy
    from policies.privacy_policy import PrivacyPolicy
    from policies.provider_selection_policy import ProviderSelectionPolicy
    from services.policy_engine import PolicyEngine
    from services.memory_platform import MemoryPlatform
    from adapters.router import Router
    from adapters.in_memory_memory_store import InMemoryMemoryStore
    from adapters.semantic_memory_stub import SemanticMemoryStub

    base_url = os.getenv("MEMORY_LIVE_BASE_URL", "http://localhost:20128/v1")
    model_id = os.getenv("MEMORY_LIVE_MODEL", "")

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
            ModelInfo(id=model_id, provider="omniroute", reasoning=True, free=True))
    if not registry.catalog():
        pytest.skip(f"live catalog empty at {base_url}")

    engine = PolicyEngine(registry)
    engine.register(BudgetPolicy())
    engine.register(PrivacyPolicy())
    engine.register(ProviderSelectionPolicy(strategy="scored"))
    router = Router(engine, {"omniroute": llm})

    session = InMemoryMemoryStore()
    longterm = InMemoryMemoryStore()
    memory = MemoryPlatform(
        session_store=session,
        long_term_store=longterm,
        semantic=SemanticMemoryStub(longterm),
    )
    return router, memory, longterm


def test_live_model_remembers_the_name(live_stack):
    from contracts.i_llm import ModelQuery

    router, memory, _ = live_stack
    sid = "live-dialogue"

    turn1 = ModelQuery(prompt="Меня зовут Алиса. Запомни это.", reasoning=False)
    memory.remember_turn(sid, turn1.prompt, role="user", importance=0.9)
    r1 = router.route(memory.augment_query(turn1, sid))
    assert r1.ok(), f"first live call failed: {r1.error}"
    memory.remember_turn(sid, r1.text, role="assistant", importance=0.4)

    turn2 = ModelQuery(prompt="Как меня зовут?", reasoning=False)
    augmented = memory.augment_query(turn2, sid)
    assert "Алиса" in augmented.prompt, "session context did not reach the prompt"

    r2 = router.route(augmented)
    assert r2.ok(), f"second live call failed: {r2.error}"

    print(f"\nlive answer: {r2.text!r} (model={r2.actual_model})")
    assert "Алис" in r2.text, f"model did not recall the name: {r2.text!r}"


def test_live_consolidation_persists_the_name(live_stack):
    _, memory, longterm = live_stack
    sid = "live-consolidate"
    memory.remember_turn(sid, "Меня зовут Алиса", role="user", importance=0.9)
    memory.remember_turn(sid, "ага", role="assistant", importance=0.1)

    report = memory.consolidate(sid)
    assert len(report.promoted) == 1, report.audit_log
    assert len(longterm) == 1

    hits = memory.recall("Алиса")
    assert hits and "Алиса" in hits[0].content
