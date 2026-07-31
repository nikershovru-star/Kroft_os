"""Wave 9 (ADR-012) Phase F — MemoryPlatform: consolidation, prompt augmentation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

from contracts.i_llm import ModelQuery
from contracts.i_memory import IMemoryStore, MemoryItem, MemoryKind, MemoryQuery
from adapters.in_memory_memory_store import InMemoryMemoryStore
from adapters.semantic_memory_stub import SemanticMemoryStub
from services.memory_platform import (
    InMemoryProceduralMemory,
    MemoryPlatform,
)


class _Fact:
    """Duck-typed stand-in for the Wave 8 Fact (read-only projection)."""
    def __init__(self, s, p, o, confidence=0.9, source="phi4"):
        self.subject, self.predicate, self.object = s, p, o
        self.confidence, self.source = confidence, source


def _platform(**kw):
    return MemoryPlatform(session_store=InMemoryMemoryStore(), **kw)


# --- session turns ---------------------------------------------------------
def test_remember_turn_tags_session_and_role():
    p = _platform()
    item = p.remember_turn("s1", "Меня зовут Алиса", role="user")
    assert MemoryKind.SESSION in item.tags
    assert "session:s1" in item.tags
    assert "role:user" in item.tags


def test_session_turns_are_isolated_per_session():
    p = _platform()
    p.remember_turn("s1", "first")
    p.remember_turn("s2", "second")
    assert [i.content for i in p.session_turns("s1")] == ["first"]


def test_session_turns_limit_returns_most_recent():
    p = _platform()
    for n in range(5):
        p.remember_turn("s1", f"turn-{n}")
    recent = p.session_turns("s1", limit=2)
    assert {i.content for i in recent} == {"turn-3", "turn-4"}


# --- prompt augmentation (Router integration) ------------------------------
def test_build_context_is_chronological_with_roles():
    p = _platform()
    p.remember_turn("s1", "Меня зовут Алиса", role="user")
    p.remember_turn("s1", "Приятно познакомиться", role="assistant")
    ctx = p.build_context("s1")
    assert ctx.index("user: Меня зовут Алиса") < ctx.index("assistant: Приятно познакомиться")


def test_augment_query_prepends_context_and_keeps_prompt():
    p = _platform()
    p.remember_turn("s1", "Меня зовут Алиса", role="user")
    original = ModelQuery(prompt="Как меня зовут?", reasoning=True, json_mode=True)
    augmented = p.augment_query(original, "s1")

    assert "Алиса" in augmented.prompt
    assert augmented.prompt.endswith("Как меня зовут?")
    # flags survive
    assert augmented.reasoning is True and augmented.json_mode is True
    # LAW 3: the caller's object is untouched
    assert original.prompt == "Как меня зовут?"
    assert augmented is not original


def test_augment_query_without_history_returns_query_unchanged():
    p = _platform()
    q = ModelQuery(prompt="cold start")
    assert p.augment_query(q, "unknown-session") is q


def test_augment_query_respects_limit():
    p = _platform()
    for n in range(6):
        p.remember_turn("s1", f"turn-{n}")
    prompt = p.augment_query(ModelQuery(prompt="q"), "s1", limit=2).prompt
    assert "turn-5" in prompt and "turn-4" in prompt
    assert "turn-0" not in prompt


# --- working memory --------------------------------------------------------
def test_working_memory_has_short_ttl_by_default():
    p = _platform()
    item = p.remember_working("scratch", "intermediate result")
    assert item.ttl == 300
    assert MemoryKind.WORKING in item.tags
    assert item.key.startswith("working:")


# --- consolidation ---------------------------------------------------------
def test_consolidation_promotes_only_important_items():
    p = _platform()
    p.remember_turn("s1", "important", importance=0.9)
    p.remember_turn("s1", "noise", importance=0.2)
    p.remember_turn("s1", "edge", importance=0.5)      # == floor -> skipped

    report = p.consolidate("s1")
    assert report.examined == 3
    assert [i.content for i in report.promoted] == ["important"]
    assert len(report.skipped) == 2
    assert report.promotion_rate == 1 / 3


def test_consolidated_items_are_tagged_and_lose_ttl():
    p = _platform()
    p.remember_turn("s1", "important", importance=0.9, ttl=60)
    promoted = p.consolidate("s1").promoted[0]
    assert MemoryKind.LONG_TERM in promoted.tags
    assert MemoryKind.CONSOLIDATED in promoted.tags
    assert promoted.ttl is None                     # long-term outlives the session
    assert promoted.key.startswith("longterm:")


def test_consolidation_explains_every_decision_law4():
    p = _platform()
    p.remember_turn("s1", "important", importance=0.9)
    p.remember_turn("s1", "noise", importance=0.1)
    log = p.consolidate("s1").audit_log
    assert any("promoted (importance 0.90" in line for line in log)
    assert any("skipped (importance 0.10" in line for line in log)
    assert any(line.startswith("summary:") for line in log)


def test_consolidation_writes_to_separate_long_term_store():
    session, longterm = InMemoryMemoryStore(), InMemoryMemoryStore()
    p = MemoryPlatform(session_store=session, long_term_store=longterm)
    p.remember_turn("s1", "important", importance=0.9)
    p.consolidate("s1")
    assert len(longterm) == 1
    assert len(session) == 1                        # session copy stays put


def test_consolidation_of_empty_session_is_safe():
    r = _platform().consolidate("nothing-here")
    assert r.examined == 0 and r.promoted == [] and r.promotion_rate == 0.0


# --- semantic retrieval ----------------------------------------------------
def test_recall_returns_empty_without_semantic_port():
    p = _platform()
    p.remember_turn("s1", "Rust is a systems language", importance=0.9)
    assert p.recall("rust") == []


def test_recall_finds_by_keyword_overlap():
    store = InMemoryMemoryStore()
    p = MemoryPlatform(session_store=store, semantic=SemanticMemoryStub(store))
    p.remember_turn("s1", "Rust is a systems language")
    p.remember_turn("s1", "Мне нравится готовить пасту")
    hits = p.recall("rust language")
    assert hits and "Rust" in hits[0].content


def test_semantic_reads_facts_from_knowledge_graph():
    """ADR-012 §2.4: graph facts are a retrieval source, injected as a callable."""
    store = InMemoryMemoryStore()
    facts = [_Fact("Rust", "is", "systems language", confidence=0.95)]
    p = MemoryPlatform(session_store=store,
                       semantic=SemanticMemoryStub(store, fact_source=lambda: facts))
    hits = p.recall("rust")
    assert hits
    assert hits[0].key.startswith("fact:")
    assert hits[0].importance == 0.95              # confidence carried over
    assert "fact" in hits[0].tags


def test_semantic_survives_broken_fact_source():
    store = InMemoryMemoryStore()

    def boom():
        raise RuntimeError("graph offline")

    p = MemoryPlatform(session_store=store, semantic=SemanticMemoryStub(store, fact_source=boom))
    store.put(MemoryItem(key="k", content="rust is fast"))
    assert p.recall("rust")                         # degraded, not dead


def test_semantic_ignores_stopword_only_query():
    store = InMemoryMemoryStore()
    store.put(MemoryItem(key="k", content="what is this"))
    assert SemanticMemoryStub(store).search("what is the") == []


# --- policy integration ----------------------------------------------------
def test_call_history_projects_into_call_records():
    p = _platform()
    p._session.put(MemoryItem(key="session:s1:call", content="call",
                              tags=("session:s1", "llm_call"), source="phi4"))
    history = p.call_history("s1")
    assert len(history) == 1 and history[0].model == "phi4"


# --- maintenance -----------------------------------------------------------
def test_cleanup_reports_expired_and_compressed_counts():
    p = _platform()
    p._session.put(MemoryItem(key="old", content="x", timestamp=time.time() - 100, ttl=1))
    p.remember_turn("s1", "noise", importance=0.1)
    stats = p.cleanup(compress_threshold=0.3)
    assert stats["expired"] == 1 and stats["compressed"] == 1


def test_cleanup_sums_both_stores():
    session, longterm = InMemoryMemoryStore(), InMemoryMemoryStore()
    stale = dict(content="x", timestamp=time.time() - 100, ttl=1)
    session.put(MemoryItem(key="a", **stale))
    longterm.put(MemoryItem(key="b", **stale))
    p = MemoryPlatform(session_store=session, long_term_store=longterm)
    assert p.cleanup()["expired"] == 2


# --- procedural memory -----------------------------------------------------
def test_procedural_records_success_rate():
    m = InMemoryProceduralMemory()
    m.record_procedure("deploy", ["build", "push"], success=True)
    m.record_procedure("deploy", ["build", "fail"], success=False)
    got = m.recall_procedure("deploy")
    assert got["runs"] == 2 and got["successes"] == 1 and got["success_rate"] == 0.5
    assert got["steps"] == ["build", "push"]        # last SUCCESSFUL steps kept


def test_procedural_unknown_returns_none():
    assert InMemoryProceduralMemory().recall_procedure("nope") is None


def test_platform_exposes_procedural_memory():
    p = _platform()
    p.record_procedure("task", ["a"], success=True)
    assert p.recall_procedure("task")["success_rate"] == 1.0
