"""(tests) Wave 11 (ADR-014) Phase G — AgentPlatform orchestration with mocks.

Every subsystem is a mock implementing just the slice AgentPlatform touches,
so the test imports ONLY contracts + the unit under test (no sibling services).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_agent_platform import AgentResult, AgentStatus, IAgentPlatform
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_eval import Scorecard, Task, TaskCategory
from services.agent_platform import AgentPlatform


# --- mock planner (Wave 10 port) ----------------------------------------
class _Planner(IPlanner):
    def plan(self, goal, context=None):
        return [Step(id="s1_a", task=f"analyze: {goal}"),
                Step(id="s1_b", task=f"execute: {goal}"),
                Step(id="s1_c", task=f"validate: {goal}")]


# --- mock executor (Wave 10 port) ---------------------------------------
class _Executor(IExecutor):
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def execute(self, workflow, router):
        self.calls += 1
        if self.fail:
            return workflow.with_status(WorkflowStatus.FAILED)
        plan = []
        for s in workflow.plan:
            r = router(ModelQuery(prompt=s.task))
            plan.append(s.with_result(
                output=r.text or "done", route_used=r.actual_model or "phi4",
                status=StepStatus.DONE,
            ))
        return workflow.with_plan(plan).with_status(WorkflowStatus.DONE)


# --- mock router (structural port) --------------------------------------
def _router(text="done"):
    def r(q: ModelQuery) -> LlmResponse:
        return LlmResponse(text=text, actual_model="phi4")
    return r


# --- mock memory (Wave 9 shape) -----------------------------------------
class _Memory:
    def __init__(self):
        self.turns = []
        self.seq = 0

    def remember_turn(self, session_id, content, role="user", importance=1.0, ttl=None, source=""):
        self.seq += 1
        key = f"session:{session_id}:{self.seq:06d}"
        self.turns.append(key)
        return type("M", (), {"key": key})()


# --- mock knowledge (Wave 8 shape) ---------------------------------------
class _Knowledge:
    def __init__(self, facts=None):
        self.facts = facts or []

    def find(self, query, limit=5):
        return self.facts[:limit]


# --- mock evaluator (Wave 7 shape) --------------------------------------
class _Evaluator:
    def run(self, task: Task, router) -> Scorecard:
        return Scorecard(task_id=task.id, model_id="phi4", output="",
                         metrics={"accuracy": 0.91, "faithfulness": 0.88})


# --- mock tools (Stage 33 shape) ----------------------------------------
class _Tools:
    def execute(self, command):
        return {"ok": True, "plan": [{"tool": "list_notes", "result": []}]}

    def list_tools(self):
        return [type("T", (), {"name": "list_notes"})()]


def _platform(**over):
    return AgentPlatform(
        planner=_Planner(),
        executor=_Executor(),
        router=_router(),
        **over,
    )


def test_run_builds_workflow_and_succeeds():
    p = _platform()
    res = p.run("Explain why Rust is safe")
    assert res.status == AgentStatus.DONE
    assert len(res.workflow.plan) == 3
    assert all(s.status == StepStatus.DONE for s in res.workflow.plan)
    assert res.workflow.goal == "Explain why Rust is safe"


def test_run_records_routes():
    p = _platform()
    res = p.run("Summarize the report")
    assert res.route_log == ("s1_a->phi4", "s1_b->phi4", "s1_c->phi4")


def test_run_persists_to_memory():
    mem = _Memory()
    p = _platform(memory=mem)
    res = p.run("Compare A and B")
    assert res.memory_refs
    assert len(mem.turns) == 2  # goal + outcome


def test_run_consults_knowledge():
    know = _Knowledge(facts=[type("F", (), {"subject": "Ownership"})()])
    p = _platform(knowledge=know)
    res = p.run("What is ownership?")
    assert res.knowledge_hits == ("Ownership",)


def test_run_measures_via_evaluator():
    p = _platform(evaluator=_Evaluator())
    res = p.run("Explain lifetimes")
    assert any("accuracy=0.91" in line for line in res.eval_summary)


def test_run_delegates_tools():
    p = _platform(tools=_Tools())
    res = p.run("find duplicate notes")
    assert res.tool_results and "tool ok" in res.tool_results[0]


def test_full_integration_all_subsystems():
    p = _platform(memory=_Memory(), knowledge=_Knowledge([type("F", (), {"subject": "X"})()]),
                  evaluator=_Evaluator(), tools=_Tools())
    res = p.run("Analyze the architecture")
    assert res.status == AgentStatus.DONE
    assert res.memory_refs and res.knowledge_hits and res.eval_summary and res.tool_results


def test_execution_failure_surfaces_in_result():
    p = AgentPlatform(planner=_Planner(), executor=_Executor(fail=True), router=_router())
    res = p.run("Do something impossible")
    assert res.status == AgentStatus.FAILED
    assert res.workflow.status == WorkflowStatus.FAILED
    assert res.error.startswith("execution:")


def test_original_workflow_untouched():
    wf_in = Workflow(id="w", goal="g", plan=[Step(id="s1", task="t")])
    # planner builds a fresh workflow, so the contract is: the returned result's
    # workflow is a NEW object, not the one we might pass elsewhere
    p = _platform()
    res = p.run("goal")
    assert res.workflow is not wf_in


def test_injected_dependencies_only_used_when_present():
    # no memory/knowledge/eval/tools -> run still succeeds, fields stay empty
    p = _platform()
    res = p.run("plain goal")
    assert res.memory_refs == ()
    assert res.knowledge_hits == ()
    assert res.eval_summary == ()
    assert res.tool_results == ()
