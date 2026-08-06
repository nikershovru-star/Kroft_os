"""(tests) Agents v0.1 — Research Agent behaviour (ADR-102, ТЗ-AGENT-BEHAVIOUR-01).

K8: this file lives in tests/ (separate from runtime, LAW 8). It exercises the REAL
agent dispatch path using the live ReferenceSearchService over a seeded graph — NOT mocks —
so the test proves the agent genuinely uses the knowledge engine instead of returning a
fixed string. LLM-free by default (I-09); the optional LLM path is covered by a mock ILlm.
"""
from contracts.i_orchestrator import OrchestrationGoal
from contracts.i_identity import AgentIdentity

from services.research_agent import ResearchAgent, ResearchAgentExecutor
from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine
from services.memory_platform import InMemoryProceduralMemory
from kernel.search import ReferenceSearchService
from kernel.memory_store import InMemoryLayeredMemory
from kernel.orchestrator import build_orchestrator
from kernel.identity import (
    ReferenceIdentityRegistry, ReferenceTrustRegistry, ReferenceActionLog,
)
from kernel.plugin import ReferencePluginRegistry
from contracts.i_llm import ILlm


def _build_research_stack(llm=None):
    """Assemble a real research agent + orchestrator over a seeded knowledge graph."""
    graph = InMemoryGraphEngine()
    memory = InMemoryLayeredMemory()
    engine = build_knowledge_engine(graph=graph, content_index=ContentIndex())
    engine.ingest(
        "adr-102",
        "# Agent Behaviour Layer\nThe orchestrator routes by specialization times trust.",
    )
    search = ReferenceSearchService(memory, graph)
    agent = ResearchAgent(search=search, llm=llm, top_k=5)
    ident = ReferenceIdentityRegistry()
    ident.register(AgentIdentity(
        agent_id="agent.research", specialization="research", trust_level=0.9))
    orch = build_orchestrator(
        identity_registry=ident,
        plugin_registry=ReferencePluginRegistry(),
        trust_registry=ReferenceTrustRegistry(),
        action_log=ReferenceActionLog(),
        agent_executor=ResearchAgentExecutor(agent),
    )
    return agent, orch


def test_research_agent_has_behaviour_surface():
    """ResearchAgent exposes the IAgentPlatform surface; Executor exposes IAgentExecutor surface.

    We check the callable surface without importing the ABCs directly (they live in a module
    with a circular import edge under pytest collection order); the ABC conformance itself is
    covered by contracts/i_agent_platform + kernel.agent_executor specs.
    """
    assert callable(getattr(ResearchAgent, "run", None))
    assert callable(getattr(ResearchAgent, "ask", None))
    assert callable(getattr(ResearchAgentExecutor, "execute", None))
    assert callable(getattr(ResearchAgentExecutor, "can_execute", None))


def test_dispatch_selects_research_agent():
    """Orchestrator.dispatch routes a 'research' capability goal to the Research Agent."""
    _, orch = _build_research_stack()
    goal = OrchestrationGoal(goal_id="g1", capability="research", payload="agent behaviour")
    outcome = orch.dispatch(goal)
    assert outcome.success, outcome.detail
    # the real agent surfaced the seeded graph node (not a delegated placeholder)
    assert "behaviour" in outcome.detail.lower(), outcome.detail


def test_research_goal_full_cycle():
    """Goal -> ResearchAgent -> ReferenceSearchService -> AgentResult with real hits."""
    agent, _ = _build_research_stack()
    result = agent.run("agent behaviour orchestrator")
    assert result.is_success
    assert result.knowledge_hits, "agent returned no knowledge hits (fixed-answer bug)"
    assert any("behaviour" in r.lower() for r in result.tool_results), result.tool_results


def test_graceful_degradation_without_llm():
    """No LLM wired: agent still succeeds using graph hits (O1, I-09 determinism)."""
    agent, _ = _build_research_stack(llm=None)
    result = agent.run("agent behaviour")
    assert result.is_success
    # tool_results must carry the retrieved content, not an error
    assert result.tool_results and "behaviour" in result.tool_results[-1].lower()


def test_optional_llm_synthesis():
    """With an LLM, the agent synthesises an answer over the retrieved hits."""

    class _FakeLlm(ILlm):
        def complete(self, prompt, **kwargs):
            return f"[synthesis] {prompt[:40]}"
        def stream(self, prompt, **kwargs):
            yield f"[synthesis] {prompt[:40]}"

    agent, _ = _build_research_stack(llm=_FakeLlm())
    result = agent.run("agent behaviour")
    assert result.is_success
    assert result.tool_results and result.tool_results[-1].startswith("[synthesis]")


def test_backward_compat_other_capabilities_untouched():
    """A non-research agent present in the registry still routes (delegated) — orchestrator intact."""
    agent, orch = _build_research_stack()
    # register a second agent so the orchestrator has an eligible executor for 'coding'
    orch._identities.register(AgentIdentity(
        agent_id="agent.coding", specialization="coding", trust_level=0.9))
    goal = OrchestrationGoal(goal_id="g2", capability="coding", payload="write a function")
    # pre-ТЗ delegated behaviour: agent present but no real executor -> delegated success=True
    outcome = orch.dispatch(goal)
    assert outcome.success, outcome.detail  # backward-compatible delegate path remains green
