"""(tests) Agents v0.1 — Writer Agent behaviour + MultiAgentExecutor routing (ADR-102).

K8: lives in tests/ (LAW 8). Exercises the REAL dispatch path with a live
ReferenceSearchService over a seeded graph — proves the writer agent genuinely uses
the knowledge graph instead of a fixed string, and that MultiAgentExecutor routes "writing".
"""
from contracts.i_orchestrator import OrchestrationGoal

from services.writer_agent import WriterAgent, WriterAgentExecutor
from services.research_agent import ResearchAgent, ResearchAgentExecutor
from services.architect_agent import ArchitectAgent, ArchitectAgentExecutor
from services.programmer_agent import ProgrammerAgent, ProgrammerAgentExecutor
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
    engine.ingest("adr-091", "# Knowledge Engine\nIngests the live vault graph for search.")
    return ReferenceSearchService(memory, graph)


def _build():
    search = _search()
    research = ResearchAgent(search=search, top_k=3)
    architect = ArchitectAgent(search=search, top_k=3)
    programmer = ProgrammerAgent(search=search, top_k=3)
    writer = WriterAgent(search=search, top_k=3)
    multi = MultiAgentExecutor([
        ResearchAgentExecutor(research),
        ArchitectAgentExecutor(architect),
        ProgrammerAgentExecutor(programmer),
        WriterAgentExecutor(writer),
    ])
    return research, architect, programmer, writer, multi


def test_writer_agent_real_search():
    """Writer agent uses the live graph, not a fixed answer."""
    _, _, _, writer, _ = _build()
    res = writer.run("agent behaviour")
    assert res.knowledge_hits, "writer returned NO knowledge hits (fixed-answer bug?)"
    answer = res.tool_results[-1].lower() if res.tool_results else ""
    assert "behaviour" in answer or "agent" in answer, res.tool_results


def test_multiagent_routes_writing():
    """MultiAgentExecutor dispatches writing -> writer."""
    _, _, _, _, multi = _build()
    out = multi.execute(OrchestrationGoal(goal_id="w1", capability="writing", payload="agent behaviour"))
    assert out.success and "behaviour" in out.detail.lower(), out.detail


def test_multiagent_can_execute_writing():
    _, _, _, _, multi = _build()
    assert multi.can_execute(OrchestrationGoal(goal_id="x", capability="writing"))


def test_writer_graceful_without_llm():
    """No LLM -> returns matched hits verbatim (LLM-free, I-09)."""
    _, _, _, writer, _ = _build()
    res = writer.run("agent behaviour")
    assert res.is_success
    assert res.tool_results and "graph:" in res.tool_results[-1]
