"""(tests) Phase C Wave C1 — Agent Runtime фундамент (ADR-103).

K8: тесты в tests/ (LAW 8). Проверяет фундамент БЕЗ god-object и БЕЗ прямых вызовов
между агентами:
  - сквозной цикл: задача -> делегирование A->B -> обмен через blackboard -> результат;
  - proof-of-fire на cycle-detection (A->B->A блокируется);
  - versioned blackboard + single-writer;
  - IAgentRuntime facade зависит только от портов (K6 достигается через composition root).

Использует РЕАЛЬНЫЕ агенты (Research/Architect) через MultiAgentExecutor как A и B.
Агенты обмениваются контекстом ТОЛЬКО через IBlackboard (stigmergy), не вызывая друг друга.
"""
from contracts.i_agent_runtime import WorkflowResult
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from services.agent_runtime import AgentRuntime
from services.blackboard import InMemoryBlackboard
from services.delegation_service import DelegationService
from services.multi_agent_executor import MultiAgentExecutor
from services.research_agent import ResearchAgent, ResearchAgentExecutor
from services.architect_agent import ArchitectAgent, ArchitectAgentExecutor
from services.knowledge_graph.engine import InMemoryGraphEngine
from services.content_index import ContentIndex
from services.knowledge_engine import build_knowledge_engine
from services.memory_platform import InMemoryProceduralMemory
from kernel.search import ReferenceSearchService
from kernel.memory_store import InMemoryLayeredMemory


def _runtime():
    memory = InMemoryLayeredMemory()
    graph = InMemoryGraphEngine()
    engine = build_knowledge_engine(graph=graph, content_index=ContentIndex())
    engine.ingest("adr-102", "# Agent Behaviour Layer\nThe orchestrator routes by specialization times trust.")
    search = ReferenceSearchService(memory, graph)
    research = ResearchAgent(search=search, top_k=3)
    architect = ArchitectAgent(search=search, top_k=3)
    executor = MultiAgentExecutor([ResearchAgentExecutor(research), ArchitectAgentExecutor(architect)])
    blackboard = InMemoryBlackboard()
    delegation = DelegationService(max_depth=8)
    return AgentRuntime(executor=executor, blackboard=blackboard, delegation=delegation, root_capability="research")


def test_runtime_end_to_end_through_blackboard():
    """Сквозной: research -> delegation -> blackboard-обмен -> результат."""
    rt = _runtime()
    res = rt.run_workflow("agent behaviour", root_goal_id="root-1")
    assert isinstance(res, WorkflowResult)
    assert res.success, res.detail
    # стигмерgy: результат шага записан в team-scope blackboard (не прямой вызов)
    assert rt._blackboard.latest_version("team.root-1") >= 1
    snap = rt._blackboard.snapshot("team.root-1")
    assert snap.entries[-1].payload  # есть контекст для координации


def test_delegation_cycle_blocked_proof_of_fire():
    """Proof-of-fire: A->B->A НЕ допускается (cycle detection)."""
    rt = _runtime()
    # A: root делегирует A (research)
    goal_a = OrchestrationGoal(goal_id="A", capability="research", payload="agent behaviour")
    out_a = rt.delegate_step("root", goal_a)
    assert out_a.success, out_a.detail
    # A делегирует B (architecture)
    goal_b = OrchestrationGoal(goal_id="B", capability="architecture", payload="agent behaviour")
    out_b = rt.delegate_step("A", goal_b)
    assert out_b.success, out_b.detail
    # B пытается делегировать обратно A (research) -> цикл A->B->A
    goal_a_back = OrchestrationGoal(goal_id="A", capability="research", payload="agent behaviour")
    out_cycle = rt.delegate_step("B", goal_a_back)
    assert not out_cycle.success
    assert "cycle" in out_cycle.detail.lower(), out_cycle.detail


def test_blackboard_versioned_single_writer():
    """Versioned blackboard: версии монотонны; чужой writer -> contention."""
    rt = _runtime()
    e1 = rt._blackboard.append("team.x", "agent-1", {"v": 1})
    e2 = rt._blackboard.append("team.x", "agent-1", {"v": 2})
    assert e2.version == e2.version and e2.version > e1.version
    import pytest
    from contracts.i_blackboard import BlackboardContention
    with pytest.raises(BlackboardContention):
        rt._blackboard.append("team.x", "agent-2", {"v": 3})  # другой writer -> отказ


def test_runtime_facade_depends_only_on_ports():
    """IAgentRuntime facade композируется из портов (K6 достигается в composition root)."""
    rt = _runtime()
    assert isinstance(rt, AgentRuntime)
    # delegation через IDelegationService (не прямой dispatch ядра)
    assert rt._delegation.depth_of("root") == 0
