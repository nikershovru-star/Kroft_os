"""(tests/agent_runtime) Phase C Wave C2 — WorkflowCoordinator + composition root (ADR-103).

K8: тесты в tests/. Проверяет:
  - build_workflow(goal) детерминирован (I-09, sha256 id);
  - choose_strategy() == stigmergy;
  - end-to-end через run_kroft boot (--agent-runtime) -> interactive_query маршрутирует
    через WorkflowCoordinator -> AgentRuntime -> blackboard;
  - без флага --agent-runtime: workflow_coordinator is None (legacy path НЕИЗМЕНЕН).
"""
import types

from contracts.i_workflow_coordinator import IWorkflowCoordinator
from services.coordination_strategy import StigmergyStrategy
from services.workflow_coordinator import WorkflowCoordinator
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


def _coordinator():
    memory = InMemoryLayeredMemory()
    graph = InMemoryGraphEngine()
    engine = build_knowledge_engine(graph=graph, content_index=ContentIndex())
    engine.ingest("adr-102", "# Agent Behaviour Layer\nThe orchestrator routes by specialization times trust.")
    search = ReferenceSearchService(memory, graph)
    research = ResearchAgent(search=search, top_k=3)
    architect = ArchitectAgent(search=search, top_k=3)
    executor = MultiAgentExecutor([ResearchAgentExecutor(research), ArchitectAgentExecutor(architect)])
    runtime = AgentRuntime(executor=executor, blackboard=InMemoryBlackboard(),
                           delegation=DelegationService(max_depth=8), root_capability="research")
    return WorkflowCoordinator(runtime=runtime, strategy=StigmergyStrategy(), root_capability="research")


def test_build_workflow_deterministic_I09():
    c = _coordinator()
    wf1 = c.build_workflow("agent behaviour")
    wf2 = c.build_workflow("agent behaviour")
    assert wf1.id == wf2.id
    assert wf1.id.startswith("wf:")
    assert len(wf1.id) == len("wf:") + 12  # sha256[:12]
    assert wf1.plan[0].task == "agent behaviour"
    assert wf1.variables["root_capability"] == "research"


def test_choose_strategy_is_stigmergy():
    c = _coordinator()
    assert c.choose_strategy().name == "stigmergy"
    assert isinstance(c, IWorkflowCoordinator)


def test_run_end_to_end_through_coordinator():
    c = _coordinator()
    wf = c.build_workflow("agent behaviour")
    out = c.run(wf)
    assert out.status == "done"
    assert out.plan[0].status == "done"
    assert out.plan[0].output  # результат из AgentRuntime (blackboard-обмен)


def test_run_kroft_agent_runtime_flag_wires_coordinator():
    """End-to-end через run_kroft --agent-runtime: boot + interactive_query маршрутирует."""
    from composition.run_kroft import KroftApp
    cfg = types.SimpleNamespace(
        node_id="nodeA", llm="none", federation=False, ticks=1, no_demo=True,
        agent_runtime=True, vault=None, interactive=False, mock_llm=False,
    )
    boot = KroftApp(cfg)
    assert boot.workflow_coordinator is not None
    answer = boot.interactive_query("agent behaviour")
    assert answer and "no answer" not in answer.lower(), answer


def test_run_kroft_without_flag_legacy_unchanged():
    """Без --agent-runtime: workflow_coordinator is None (legacy path не трогается)."""
    from composition.run_kroft import KroftApp
    cfg = types.SimpleNamespace(
        node_id="nodeA", llm="none", federation=False, ticks=1, no_demo=True,
        agent_runtime=False, vault=None, interactive=False, mock_llm=False,
    )
    boot = KroftApp(cfg)
    assert boot.workflow_coordinator is None
    # legacy path работает (возвращает ответ или no-hits, не падает)
    res = boot.interactive_query("agent behaviour")
    assert isinstance(res, str)
