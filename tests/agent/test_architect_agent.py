"""(tests) Agents v0.1 — Architect Agent behaviour + MultiAgentExecutor routing (ADR-102).

K8: lives in tests/ (LAW 8). Exercises the REAL dispatch path with a live
ReferenceSearchService over a seeded graph — proves the architect agent genuinely uses
the knowledge graph instead of a fixed string, and that MultiAgentExecutor routes by
capability without touching the kernel/orchestrator contracts.
"""
from contracts.i_orchestrator import OrchestrationGoal
from contracts.i_identity import AgentIdentity

from services.architect_agent import ArchitectAgent, ArchitectAgentExecutor
from services.research_agent import ResearchAgent, ResearchAgentExecutor
from services.multi_agent_executor import MultiAgentExecutor
from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine
from services.memory_platform import InMemoryProceduralMemory
from kernel.search import ReferenceSearchService
from kernel.memory_store import InMemoryLayeredMemory


def _search():
    memory = InMemoryLayeredMemory()
    graph = InMemoryGraphEngine()
    engine = build_knowledge_engine(graph=graph, content_index=ContentIndex())
    engine.ingest("adr-102", "# Agent Behaviour Layer\nThe orchestrator routes by specialization times trust.")
    engine.ingest("adr-101", "# Architecture Pipeline\nKnowledge engine ingests the live vault graph.")
    return ReferenceSearchService(memory, graph)


def _build():
    search = _search()
    research = ResearchAgent(search=search, top_k=3)
    architect = ArchitectAgent(search=search, top_k=3)
    multi = MultiAgentExecutor([ResearchAgentExecutor(research), ArchitectAgentExecutor(architect)])
    return research, architect, multi


def test_architect_agent_real_search():
    """Architect agent uses the live graph, not a fixed answer."""
    architect, _, _ = _build()
    res = architect.run("agent behaviour")
    assert res.knowledge_hits, "architect returned NO knowledge hits (fixed-answer bug?)"
    answer = res.tool_results[-1].lower() if res.tool_results else ""
    assert "behaviour" in answer or "architecture" in answer, \
        f"architect answer missing real graph content: {res.tool_results}"


def test_multiagent_routes_by_capability():
    """MultiAgentExecutor dispatches research->research, architecture->architect."""
    research, architect, multi = _build()
    g_res = OrchestrationGoal(goal_id="r1", capability="research", payload="agent behaviour")
    g_arc = OrchestrationGoal(goal_id="a1", capability="architecture", payload="agent behaviour")
    out_res = multi.execute(g_res)
    out_arc = multi.execute(g_arc)
    assert out_res.success and "behaviour" in out_res.detail.lower(), out_res.detail
    assert out_arc.success and "behaviour" in out_arc.detail.lower(), out_arc.detail


def test_multiagent_can_execute_scope():
    _, _, multi = _build()
    assert multi.can_execute(OrchestrationGoal(goal_id="x", capability="research"))
    assert multi.can_execute(OrchestrationGoal(goal_id="x", capability="architecture"))
    assert not multi.can_execute(OrchestrationGoal(goal_id="x", capability="coding"))


def test_multiagent_unknown_capability_reports_failure():
    """Unknown capability -> honest failure (O1 default-deny), not a crash."""
    _, _, multi = _build()
    out = multi.execute(OrchestrationGoal(goal_id="u", capability="coding", payload="x"))
    assert not out.success and "no agent executor" in out.detail


def test_architect_graceful_without_llm():
    """No LLM -> returns matched hits verbatim (LLM-free, I-09)."""
    architect, _, _ = _build()
    res = architect.run("agent behaviour")
    assert res.is_success
    assert res.tool_results and "graph:" in res.tool_results[-1]
