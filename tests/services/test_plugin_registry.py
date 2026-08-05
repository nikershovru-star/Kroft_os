"""K8 tests for ТЗ-PLUGIN-01 — deterministic plugin registry (LLM-free, standalone).

Covers (acceptance + O1/K1/K6/K8 + ADR-071):
- register/list/get/invoke deterministic (I-09); list() stable order (sorted by id).
- invoke returns PluginResult (ok + payload).
- unregister removes the plugin; unknown-id unregister is a safe no-op.
- duplicate register -> PluginInvocationError (handled, not silent).
- negative: unknown id invoke -> PluginResult(ok=False, error=...).
- O1: reference plugins are read-only w.r.t. HARD — they only call ISearchService /
  IResearchService, never mutate HARD/FSM/contracts; registry never mutates plugins.
- composition: SearchPlugin/ResearchPlugin wrap existing ports (no duplication).
- existing test_plugins.py (CLI IPlugin) remains green (run separately).

Флаг C: registry standalone (build_plugin_registry), no build_kernel dependency.
Флаг LLM-01: PluginResult/PluginManifest frozen VOs with real types.
"""

from __future__ import annotations

from contracts.plugin import (
    ICapabilityPlugin,
    IPluginRegistry,
    PluginInvocationError,
    PluginManifest,
    PluginResult,
)
from kernel.memory_store import InMemoryLayeredMemory
from kernel.plugin import (
    ReferencePluginRegistry,
    ResearchPlugin,
    SearchPlugin,
    build_plugin_registry,
)
from kernel.research import ReferenceResearchService, build_research_service
from kernel.search import build_search_service
from services.knowledge_graph.engine import InMemoryGraphEngine
from contracts.cognitive_domain import (
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
    SemanticFact,
)
from contracts.i_search import SearchScope
from contracts.knowledge_graph import Node, NodeType


def _search_service():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("S")
    mem.commit_semantic(SemanticFact(
        id="sf-blue", content="choose blue when sky is clear",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    mem.commit_semantic(SemanticFact(
        id="sf-red", content="avoid red because it fails often",
        confidence=ConfidenceScore(0.6, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    g = InMemoryGraphEngine()
    g.add_node(Node(id="adr65", type=NodeType.ADR, label="ADR-065 llm advisor boundary"))
    return build_search_service(mem, g)


def _registry():
    search = _search_service()
    rs = ReferenceResearchService(search)
    return build_plugin_registry(SearchPlugin(search), ResearchPlugin(rs))


# ---------------------------------------------------------------------------
# 1. register / list / get deterministic
# ---------------------------------------------------------------------------
def test_register_then_list_sorted_by_id():
    reg = _registry()
    ids = [m.id for m in reg.list()]
    assert ids == sorted(ids)  # stable, deterministic order
    assert set(ids) == {"research", "search"}


def test_get_returns_plugin():
    reg = _registry()
    p = reg.get("search")
    assert isinstance(p, ICapabilityPlugin)
    assert p.id == "search"
    assert reg.has("search") and not reg.has("nope")


# ---------------------------------------------------------------------------
# 2. invoke returns PluginResult
# ---------------------------------------------------------------------------
def test_invoke_search_returns_pluginresult():
    reg = _registry()
    res = reg.invoke("search", {"query": "blue red"})
    assert isinstance(res, PluginResult)
    assert res.ok is True
    assert isinstance(res.payload, list) and len(res.payload) == 2


def test_invoke_research_returns_summary():
    reg = _registry()
    res = reg.invoke("research", {"query": "blue red"})
    assert res.ok is True
    assert "summary" in res.payload and res.payload["findings"]


# ---------------------------------------------------------------------------
# 3. determinism (I-09)
# ---------------------------------------------------------------------------
def test_invoke_deterministic():
    reg = _registry()
    a = reg.invoke("search", {"query": "blue red"})
    b = reg.invoke("search", {"query": "blue red"})
    assert a.payload == b.payload


# ---------------------------------------------------------------------------
# 4. unregister removes; unknown unregister is safe no-op
# ---------------------------------------------------------------------------
def test_unregister_removes_plugin():
    reg = ReferencePluginRegistry()
    search = _search_service()
    reg.register(SearchPlugin(search))
    assert reg.has("search")
    reg.unregister("search")
    assert not reg.has("search")
    assert reg.get("search") is None


def test_unregister_unknown_is_noop():
    reg = ReferencePluginRegistry()
    reg.unregister("ghost")  # must not raise
    assert reg.list() == []


# ---------------------------------------------------------------------------
# 5. duplicate register handled
# ---------------------------------------------------------------------------
def test_duplicate_register_raises():
    reg = ReferencePluginRegistry()
    search = _search_service()
    reg.register(SearchPlugin(search))
    try:
        reg.register(SearchPlugin(search))  # same id -> handled error
        raise AssertionError("expected PluginInvocationError")
    except PluginInvocationError:
        pass


# ---------------------------------------------------------------------------
# 6. negative: unknown id invoke -> PluginResult(ok=False, error)
# ---------------------------------------------------------------------------
def test_unknown_id_invoke_returns_error_result():
    reg = _registry()
    res = reg.invoke("does-not-exist", {"query": "x"})
    assert isinstance(res, PluginResult)
    assert res.ok is False
    assert res.error and "unknown plugin id" in res.error


def test_invoke_bad_args_handled():
    reg = _registry()
    res = reg.invoke("search", {"wrong": "key"})  # missing 'query'
    assert res.ok is False and res.error


# ---------------------------------------------------------------------------
# 7. O1: read-only w.r.t. HARD; composition wraps existing ports
# ---------------------------------------------------------------------------
def test_plugins_wrap_existing_ports_no_duplication():
    search = _search_service()
    sp = SearchPlugin(search)
    assert isinstance(sp, ICapabilityPlugin)
    # capabilities declared, invoke reads only
    assert "retrieval" in sp.capabilities
    res = sp.invoke({"query": "blue red"})
    assert res.ok and len(res.payload) == 2


def test_registry_never_mutates_plugins():
    reg = ReferencePluginRegistry()
    search = _search_service()
    sp = SearchPlugin(search)
    reg.register(sp)
    # registry internals replaced? plugin object identity preserved
    assert reg.get("search") is sp


def test_research_plugin_readonly_no_writeback():
    # research service built WITHOUT write_back -> plugin invocation must not grow memory
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("S")
    mem.commit_semantic(SemanticFact(
        id="sf-blue", content="choose blue when sky is clear",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    g = InMemoryGraphEngine()
    search = build_search_service(mem, g)
    rs = ReferenceResearchService(search)  # write_back defaults False
    res = ResearchPlugin(rs).invoke({"query": "blue"})
    assert res.ok is True
    assert len(mem.get_semantic()) == 1  # unchanged -> read-only w.r.t. memory/HARD


# ---------------------------------------------------------------------------
# 8. factory standalone (Флаг C)
# ---------------------------------------------------------------------------
def test_build_plugin_registry_standalone():
    reg = build_plugin_registry(SearchPlugin(_search_service()))
    assert isinstance(reg, IPluginRegistry)
    assert reg.invoke("search", {"query": "blue red"}).ok is True
