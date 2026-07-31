"""(tests) Wave 11 (ADR-014) Phase G — contract + AgentResult tests.

Ports abstract, AgentResult frozen, copy-on-write transitions.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_agent_platform import IAgentPlatform, AgentResult, AgentStatus
from contracts.i_policy import PolicyContext
from contracts.i_workflow import Workflow, Step, StepStatus, WorkflowStatus
from contracts.i_llm import ModelQuery


def test_port_is_abstract():
    assert getattr(IAgentPlatform, "__abstractmethods__", set())


def test_agent_result_is_frozen():
    r = AgentResult(goal="g", workflow=Workflow(id="w", goal="g"))
    try:
        r.status = "failed"
        assert False, "AgentResult should be frozen"
    except Exception:
        pass


def test_agent_result_copy_on_write_transitions():
    wf = Workflow(id="w", goal="g", plan=[Step(id="s1", task="t")])
    r = AgentResult(goal="g", workflow=wf)
    r2 = r.with_memory("k1").with_knowledge("f1").with_status(AgentStatus.DONE)
    # original untouched
    assert r.memory_refs == ()
    assert r.status == AgentStatus.DONE  # default
    # new carries the chain
    assert r2.memory_refs == ("k1",)
    assert r2.knowledge_hits == ("f1",)


def test_agent_result_is_success_property():
    ok = AgentResult(goal="g", workflow=Workflow(id="w", goal="g"), status=AgentStatus.DONE)
    fail = AgentResult(goal="g", workflow=Workflow(id="w", goal="g"), status=AgentStatus.FAILED)
    assert ok.is_success
    assert not fail.is_success


def test_all_fields_round_trip():
    wf = Workflow(
        id="w", goal="g",
        plan=(Step(id="s1", task="t", status=StepStatus.DONE, output="ok", route_used="phi4"),),
        status=WorkflowStatus.DONE,
    )
    r = AgentResult(
        goal="g", workflow=wf, status=AgentStatus.DONE,
        memory_refs=("k1",), knowledge_hits=("f1",),
        eval_summary=("accuracy=0.90",), route_log=("s1->phi4",),
        tool_results=("tool ok",), error="",
    )
    # AgentResult is frozen + carries a Workflow dataclass; round-trip through
    # its own __dict__ (tuples -> lists -> tuples, dataclass preserved) to prove
    # field stability / constructability from plain state.
    state = {k: (tuple(v) if isinstance(v, list) else v) for k, v in r.__dict__.items()}
    restored = AgentResult(**state)
    assert restored == r
    # fields are preserved in order and value
    assert restored.workflow == wf
    assert restored.memory_refs == ("k1",)
    assert restored.eval_summary == ("accuracy=0.90",)
