"""Wave 9 (ADR-012) Phase F — integration: Router + Session Memory + Knowledge.

Offline (mock ILlm). Proves ADR-012 §2.4 end to end:
    Session Memory -> ModelQuery.prompt -> Router -> LLM "remembers"
    Session Memory -> consolidate() -> Long-Term -> Semantic retrieval
    Knowledge Graph facts -> Semantic retrieval (read-only)
"""
from tests._repo_root import repo_root
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_memory import MemoryKind
from contracts.i_policy import PolicyContext
from contracts.model_registry import ModelRegistry
from infrastructure.graph_builder import InMemoryGraphBuilder
from policies.budget_policy import BudgetPolicy
from policies.privacy_policy import PrivacyPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from services.knowledge_platform import HeuristicValidator, KnowledgePlatform
from services.memory_platform import MemoryPlatform
from adapters.router import Router
from adapters.graph_knowledge_store import GraphKnowledgeStore
from adapters.llm_entity_extractor import LLMEntityExtractor
from adapters.in_memory_memory_store import InMemoryMemoryStore
from adapters.semantic_memory_stub import SemanticMemoryStub


class _EchoLLM(ILlm):
    """Answers 'Алиса' only if the prompt actually carries that context."""

    def __init__(self, payload=None):
        self.payload = payload
        self.prompts = []

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.prompts.append(query.prompt)
        if self.payload is not None:
            text = self.payload
        elif "Алиса" in query.prompt:
            text = "Вас зовут Алиса"
        else:
            text = "Не знаю, вы не представились"
        return LlmResponse(text=text, model=query.preferred_provider or "mock",
                           actual_model=query.preferred_provider or "mock",
                           trace_id="tr-mem", latency_ms=10.0, cost=0.0)

    def stream(self, query):
        yield self.complete(query).text


def _router(llm):
    reg = ModelRegistry()
    reg.register_model(ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False,
                                 context_window=128000, free=False, cost_per_1k=5.0))
    reg.register_model(ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True,
                                 context_window=16000, free=True, cost_per_1k=0.0))
    eng = PolicyEngine(reg)
    eng.register(BudgetPolicy())
    eng.register(PrivacyPolicy())
    eng.register(ProviderSelectionPolicy(strategy="scored"))
    return Router(eng, {"omniroute": llm, "ollama": llm})


# --- the headline behaviour ------------------------------------------------
def test_llm_forgets_without_memory():
    """Control case: no memory -> the model cannot know the name."""
    llm = _EchoLLM()
    router = _router(llm)
    router.route(ModelQuery(prompt="Меня зовут Алиса"))
    answer = router.route(ModelQuery(prompt="Как меня зовут?"))
    assert "Не знаю" in answer.text


def test_llm_remembers_with_session_memory():
    """ADR-012 §2.4: Session Memory augments the prompt, the model 'remembers'."""
    llm = _EchoLLM()
    router = _router(llm)
    mem = MemoryPlatform(session_store=InMemoryMemoryStore())
    sid = "dialogue-1"

    first = ModelQuery(prompt="Меня зовут Алиса")
    mem.remember_turn(sid, first.prompt, role="user", importance=0.9)
    r1 = router.route(mem.augment_query(first, sid))
    mem.remember_turn(sid, r1.text, role="assistant", importance=0.4)

    second = ModelQuery(prompt="Как меня зовут?")
    r2 = router.route(mem.augment_query(second, sid))

    assert "Алиса" in r2.text
    assert "Меня зовут Алиса" in llm.prompts[-1]     # context really travelled
    assert llm.prompts[-1].endswith("Как меня зовут?")


def test_memory_does_not_leak_across_sessions():
    llm = _EchoLLM()
    router = _router(llm)
    mem = MemoryPlatform(session_store=InMemoryMemoryStore())
    mem.remember_turn("alice-session", "Меня зовут Алиса", role="user")

    answer = router.route(mem.augment_query(ModelQuery(prompt="Как меня зовут?"), "bob-session"))
    assert "Не знаю" in answer.text


# --- consolidation across the session boundary -----------------------------
def test_consolidated_memory_survives_and_is_retrievable():
    session, longterm = InMemoryMemoryStore(), InMemoryMemoryStore()
    mem = MemoryPlatform(
        session_store=session,
        long_term_store=longterm,
        semantic=SemanticMemoryStub(longterm),
    )
    mem.remember_turn("s1", "Меня зовут Алиса", role="user", importance=0.9)
    mem.remember_turn("s1", "ок", role="assistant", importance=0.1)

    report = mem.consolidate("s1")
    assert len(report.promoted) == 1

    hits = mem.recall("Алиса")
    assert hits and "Алиса" in hits[0].content
    assert MemoryKind.CONSOLIDATED in hits[0].tags


# --- Knowledge (Wave 8) as a retrieval source ------------------------------
def test_semantic_memory_reads_graph_facts():
    """Wave 8 facts feed Wave 9 retrieval — via callable, no service import."""
    llm = _EchoLLM(payload=json.dumps(
        [{"subject": "Rust", "predicate": "is", "object": "systems language"}]))
    router = _router(llm)

    graph = GraphKnowledgeStore(InMemoryGraphBuilder())
    knowledge = KnowledgePlatform(
        extractor=LLMEntityExtractor(router.route),
        validator=HeuristicValidator(min_confidence=0.5),
        graph=graph,
        min_confidence=0.7,
    )
    knowledge.ingest("Rust is a systems language.", document_id="doc-1")
    assert knowledge.facts(), "precondition: the graph must hold a fact"

    longterm = InMemoryMemoryStore()
    mem = MemoryPlatform(
        session_store=InMemoryMemoryStore(),
        long_term_store=longterm,
        semantic=SemanticMemoryStub(longterm, fact_source=knowledge.facts),
    )

    hits = mem.recall("rust language")
    assert hits, "graph fact should be retrievable through semantic memory"
    assert hits[0].key.startswith("fact:")
    assert "Rust" in hits[0].content


# --- policy integration ----------------------------------------------------
def test_call_history_can_feed_policy_context():
    mem = MemoryPlatform(session_store=InMemoryMemoryStore())
    mem._session.put(__import__("contracts.i_memory", fromlist=["MemoryItem"]).MemoryItem(
        key="session:s1:c1", content="call", tags=("session:s1", "llm_call"), source="phi4"))
    ctx = PolicyContext(query=ModelQuery(prompt="hi"), history=mem.call_history("s1"))
    assert len(ctx.history) == 1 and ctx.history[0].model == "phi4"


# --- layering guard --------------------------------------------------------
def test_memory_service_imports_contracts_only():
    """LAW 2 + Wave 9 DoD: the platform is engine-independent."""
    import ast
    from pathlib import Path

    src = repo_root() / "services" / "memory_platform.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
    assert "adapters" not in mods
    assert "infrastructure" not in mods
    assert "services" not in mods
