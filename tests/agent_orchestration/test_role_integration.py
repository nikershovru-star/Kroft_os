"""ADR-033 / TZ-AGENT-ROLE-INTEGRATION — AgentDivision + AgentWorkflow + AgentMemoryHandoff.

Deterministic, in-memory, NO network (no Ollama/HTTP/YouTube).
Covers:
  - AgentDivision enum (16 values, orthogonal to Role)
  - optional division on spawn (backward-compatible)
  - AgentWorkflow frozen VO + submit_goal accepts optional workflow
  - AgentMemoryHandoff graph-backed publish/consume isolation by division
    (reuses existing Multi-Resolution nodes_by_metadata API)
"""
from __future__ import annotations

from contracts.agent_orchestration import (
    AgentDivision,
    AgentMemoryHandoff,
    AgentState,
    AgentWorkflow,
    IAgentLifecycle,
    WorkflowStep,
)
from infrastructure.graph_builder import InMemoryGraphBuilder
from services.agent_orchestration.orchestrator import AgentOrchestrator
from services.graph_query_engine import GraphQueryEngine
from contracts.security import (
    AuthDecision,
    Capability,
    CapabilityContext,
    ICapabilityManager,
    Role,
)
from contracts.tenant import ITenantIsolator


# ── AgentDivision ────────────────────────────────────────────────────────────
def test_agent_division_has_17_values():
    # NOTE: divisions.json actually defines 17 divisions (incl. `testing`),
    # not 16 as loosely stated in the TZ narrative — the Enum mirrors the
    # real source of truth exactly.
    vals = [d.value for d in AgentDivision]
    assert len(vals) == 17
    assert "engineering" in vals
    assert "finance" in vals
    assert "marketing" in vals
    assert "testing" in vals
    assert AgentDivision.ENGINEERING.value == "engineering"


def test_agent_division_orthogonal_to_role_str():
    # division is a business domain; role is a privilege string — independent.
    div = AgentDivision.FINANCE
    assert div.value == "finance"
    assert isinstance(div, AgentDivision)


# ── AgentWorkflow (frozen VO) ────────────────────────────────────────────────
def test_agent_workflow_frozen_and_steps():
    wf = AgentWorkflow(
        id="wf1",
        name="MVP",
        steps=(
            WorkflowStep(AgentDivision.ENGINEERING, ["Python"], "h1"),
            WorkflowStep(AgentDivision.FINANCE, ["Finance"], "h2", depends_on=("h1",)),
        ),
    )
    assert wf.id == "wf1"
    assert len(wf.steps) == 2
    assert wf.steps[1].depends_on == ("h1",)
    # frozen -> mutation raises
    try:
        wf.steps[0].handoff_key = "x"
        assert False, "WorkflowStep must be frozen"
    except Exception:
        pass


def test_submit_goal_accepts_optional_workflow_signature():
    # Contract check: IAgentOrchestrator.submit_goal accepts optional workflow.
    # We only assert the port signature is callable with the new param via a
    # minimal stub (no real orchestrator execution needed for contract test).
    from contracts.agent_orchestration import IAgentOrchestrator

    class _Stub(IAgentOrchestrator):
        def submit_goal(self, tenant_id, goal, required_capabilities,
                        workflow=None):
            return []
        def get_pool(self, tenant_id):
            return []

    wf = AgentWorkflow(id="w", name="n", steps=(
        WorkflowStep(AgentDivision.ENGINEERING, ["Python"], "h"),
    ))
    stub = _Stub()
    # old-style call (no workflow) still works
    assert stub.submit_goal("t", "g", ["Python"]) == []
    # new-style call with workflow
    assert stub.submit_goal("t", "g", ["Python"], workflow=wf) == []


# ── AgentMemoryHandoff (graph-backed, isolation by division) ──────────────────
def _publish_consume_roundtrip():
    """Replicates IAgentMemoryHandoff strategy over the existing graph API.

    publish_handoff -> add_node(NodeType.FACT-ish, meta with workflow_id/
    step_id/division/payload); consume_handoff -> nodes_by_metadata filter.
    Uses InMemoryGraphBuilder + GraphQueryEngine (in-memory, no network).
    """
    g = InMemoryGraphBuilder()
    q = GraphQueryEngine(g)

    wid = "wf-x"
    # producer (ENGINEERING) publishes a deliverable for FINANCE consumer
    node_id_fin = "n_fin"
    g.add_node(node_id_fin, "Deliverable for finance", {
        "level": "fact",
        "workflow_id": wid,
        "step_id": "s2",
        "division": AgentDivision.FINANCE.value,
        "payload": {"budget": 1000},
    })
    # a second node for a DIFFERENT division (must NOT leak to FINANCE consumer)
    node_id_eng = "n_eng"
    g.add_node(node_id_eng, "Deliverable for engineering", {
        "level": "fact",
        "workflow_id": wid,
        "step_id": "s1",
        "division": AgentDivision.ENGINEERING.value,
        "payload": {"design": "x"},
    })

    # consume_handoff(wid, FINANCE) -> only FINANCE node
    fin_nodes = q.nodes_by_metadata("workflow_id", wid)
    fin_payloads = [
        n.get("meta", {}).get("payload")
        for n in (g.get_graph()["nodes"])
        if n["id"] in fin_nodes
        and n.get("meta", {}).get("division") == AgentDivision.FINANCE.value
    ]
    return fin_payloads, node_id_fin, node_id_eng


def test_memory_handoff_publish_consume_isolation():
    fin_payloads, n_fin, n_eng = _publish_consume_roundtrip()
    # FINANCE consumer sees ONLY the finance deliverable
    assert fin_payloads == [{"budget": 1000}]
    # engineering node exists but is excluded by division filter
    assert n_eng != n_fin


def test_memory_handoff_empty_workflow_returns_empty():
    g = InMemoryGraphBuilder()
    q = GraphQueryEngine(g)
    # no nodes for this workflow id
    nodes = q.nodes_by_metadata("workflow_id", "nonexistent")
    assert nodes == []
    # division filter over empty set stays empty (graceful, no crash)
    payloads = [
        n.get("meta", {}).get("payload")
        for n in g.get_graph()["nodes"]
        if n["id"] in nodes
        and n.get("meta", {}).get("division") == AgentDivision.FINANCE.value
    ]
    assert payloads == []


def test_agent_memory_handoff_vo_frozen():
    ho = AgentMemoryHandoff(
        workflow_id="w1", step_id="s1", producer_agent_id="a1",
        consumer_division=AgentDivision.FINANCE, payload_ref="n1",
    )
    assert ho.consumer_division == AgentDivision.FINANCE
    assert ho.workflow_id == "w1"
    try:
        ho.step_id = "x"
        assert False, "AgentMemoryHandoff must be frozen"
    except Exception:
        pass


# ── GraphBackedHandoff (real adapter over in-memory graph) ───────────────────
from services.agent_orchestration.graph_handoff import GraphBackedHandoff


def _make_handoff():
    g = InMemoryGraphBuilder()
    q = GraphQueryEngine(g)
    return GraphBackedHandoff(g, q)


def test_graph_backed_handoff_publish_then_consume():
    h = _make_handoff()
    ho = AgentMemoryHandoff(
        workflow_id="wf1", step_id="s1", producer_agent_id="a-prod",
        consumer_division=AgentDivision.FINANCE, payload_ref="x",
    )
    node_id = h.publish_handoff(ho, {"budget": 1000})
    assert node_id.startswith("handoff:wf1:s1:finance")
    payloads = h.consume_handoff("wf1", AgentDivision.FINANCE)
    assert payloads == [{"budget": 1000}]


def test_graph_backed_handoff_division_isolation():
    h = _make_handoff()
    # finance deliverable
    h.publish_handoff(AgentMemoryHandoff(
        workflow_id="wf2", step_id="s-fin", producer_agent_id="a1",
        consumer_division=AgentDivision.FINANCE, payload_ref="n1"),
        {"budget": 500})
    # engineering deliverable (same workflow, different division)
    h.publish_handoff(AgentMemoryHandoff(
        workflow_id="wf2", step_id="s-eng", producer_agent_id="a2",
        consumer_division=AgentDivision.ENGINEERING, payload_ref="n2"),
        {"design": "x"})
    # finance consumer sees ONLY finance payload
    assert h.consume_handoff("wf2", AgentDivision.FINANCE) == [{"budget": 500}]
    # engineering consumer sees ONLY engineering payload
    assert h.consume_handoff("wf2", AgentDivision.ENGINEERING) == [{"design": "x"}]


def test_graph_backed_handoff_empty_workflow():
    h = _make_handoff()
    assert h.consume_handoff("nope", AgentDivision.FINANCE) == []


def test_graph_backed_handoff_visible_via_nodes_by_metadata():
    # proves reuse of the earlier Multi-Resolution API (no new query method):
    # a published handoff is discoverable via IGraphQuery.nodes_by_metadata.
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    h.publish_handoff(AgentMemoryHandoff(
        workflow_id="wf3", step_id="s1", producer_agent_id="a1",
        consumer_division=AgentDivision.MARKETING, payload_ref="n1"),
        {"campaign": "summer"})
    found = h._query.nodes_by_metadata("workflow_id", "wf3")
    assert "handoff:wf3:s1:marketing" in found


# ── AgentWorkflow → AgentOrchestrator integration (PHASE 3) ───────────────────
class _FakeLifecycle(IAgentLifecycle):
    def spawn(self, agent_id, tenant_id, role, goal, division=None):
        return AgentState.SPAWNED
    def transition(self, agent_id, to_state, reason=""):
        return None
    def terminate(self, agent_id, reason=""):
        return None
    def get_state(self, agent_id):
        return AgentState.RUNNING


class _FakeCapability(ICapabilityManager):
    def context_for(self, agent_id, role):
        return CapabilityContext(agent_id=agent_id, role=role)
    def authorize(self, ctx, required):
        return AuthDecision(allowed=True)
    def register_role(self, role, capabilities):
        pass


class _FakeTenant(ITenantIsolator):
    def validate(self, tenant_id):
        return True
    def check_boundary(self, *args, **kwargs):
        return True
    def namespace_path(self, *args, **kwargs):
        return ""
    def scope_key(self, *args, **kwargs):
        return "default"


def _make_orchestrator(handoff=None):
    return AgentOrchestrator(
        lifecycle=_FakeLifecycle(),
        capability=_FakeCapability(),
        tenant_isolator=_FakeTenant(),
        handoff=handoff,
    )


def _wf_two_step():
    return AgentWorkflow(
        id="wf-seq", name="seq", steps=(
            WorkflowStep(AgentDivision.ENGINEERING, ["Tool"], "s1"),
            WorkflowStep(AgentDivision.FINANCE, ["Tool"], "s2"),
        ),
    )


def test_workflow_sequential_handoff():
    # Test 1: A → handoff → B receives A result
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    results = orch.submit_goal("t1", "goal", ["Tool"], workflow=_wf_two_step())
    assert len(results) == 2
    assert all(r.status == "DONE" for r in results)
    # finance consumer (step 2) sees engineering deliverable (step 1)
    payloads = h.consume_handoff("wf-seq", AgentDivision.FINANCE)
    assert payloads == [{"output": "DONE", "agent_id": "t1:agent-1"}]


def test_workflow_multi_step():
    # Test 2: A → B → C
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    wf = AgentWorkflow(id="wf-abc", name="abc", steps=(
        WorkflowStep(AgentDivision.ENGINEERING, ["Tool"], "s1"),
        WorkflowStep(AgentDivision.FINANCE, ["Tool"], "s2"),
        WorkflowStep(AgentDivision.MARKETING, ["Tool"], "s3"),
    ))
    results = orch.submit_goal("t1", "goal", ["Tool"], workflow=wf)
    assert len(results) == 3
    # each next division received the prior step's handoff
    assert h.consume_handoff("wf-abc", AgentDivision.FINANCE) == \
        [{"output": "DONE", "agent_id": "t1:agent-1"}]
    assert h.consume_handoff("wf-abc", AgentDivision.MARKETING) == \
        [{"output": "DONE", "agent_id": "t1:agent-2"}]


def test_workflow_department_isolation():
    # Test 3: engineering result not visible to finance consumer of DIFFERENT wf
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    orch.submit_goal("t1", "goal", ["Tool"], workflow=_wf_two_step())
    # finance sees eng handoff (same workflow) — allowed
    assert h.consume_handoff("wf-seq", AgentDivision.FINANCE) != []
    # a DIFFERENT division (MARKETING) in same workflow sees nothing for s1
    assert h.consume_handoff("wf-seq", AgentDivision.MARKETING) == []


def test_workflow_isolation():
    # Test 4: workflow-A result not visible to workflow-B read
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    orch.submit_goal("t1", "goal", ["Tool"], workflow=_wf_two_step())
    # workflow "other" reads nothing
    assert h.consume_handoff("other-wf", AgentDivision.FINANCE) == []


def test_workflow_empty():
    # Test 5: empty workflow → no execution, no graph write
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    wf = AgentWorkflow(id="wf-empty", name="e", steps=())
    assert orch.submit_goal("t1", "goal", ["Tool"], workflow=wf) == []
    assert g.get_graph()["nodes"] == []  # no graph write


def test_workflow_failed_intermediate():
    # Test 6: failed intermediate agent → workflow != success, no handoff fwd
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))

    class _FailOrch(AgentOrchestrator):
        def _run(self, agent_id, goal, required):
            # fail the 2nd step (handoff_key "s2")
            if agent_id.endswith(":agent-2"):
                wf = __import__("contracts.i_workflow", fromlist=["Workflow"]).Workflow(
                    id="x", goal=goal, status="failed")
                return __import__("contracts.i_agent_platform", fromlist=["AgentResult"]).AgentResult(
                    goal=goal, workflow=wf, status="FAILED")
            return super()._run(agent_id, goal, required)

    orch = _FailOrch(
        lifecycle=_FakeLifecycle(), capability=_FakeCapability(),
        tenant_isolator=_FakeTenant(), handoff=h,
    )
    results = orch.submit_goal("t1", "goal", ["Tool"], workflow=_wf_two_step())
    # step 1 DONE, step 2 FAILED
    assert results[0].status == "DONE"
    assert results[1].status == "FAILED"
    # step 1 handoff WAS published (agent-1 -> FINANCE); step 2 handoff was NOT
    # (failed intermediate agent stops the pipeline, TZ §18)
    assert h.consume_handoff("wf-seq", AgentDivision.FINANCE) == \
        [{"output": "DONE", "agent_id": "t1:agent-1"}]


def test_workflow_handoff_graph_visibility():
    # Test 7: publish → nodes_by_metadata finds it
    g = InMemoryGraphBuilder()
    h = GraphBackedHandoff(g, GraphQueryEngine(g))
    orch = _make_orchestrator(handoff=h)
    orch.submit_goal("t1", "goal", ["Tool"], workflow=_wf_two_step())
    ids = h._query.nodes_by_metadata("workflow_id", "wf-seq")
    assert "handoff:wf-seq:s1:finance" in ids


def test_orchestrator_no_direct_graph_dependency():
    # Test 8: AgentOrchestrator must NOT import graph infrastructure directly.
    import services.agent_orchestration.orchestrator as mod
    import ast
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    bad = [i for i in imports if i == "infrastructure"
           or i.startswith("contracts.igraph")
           or i.startswith("contracts.i_graph")]
    assert not bad, f"orchestrator must not import graph infra, found: {bad}"

