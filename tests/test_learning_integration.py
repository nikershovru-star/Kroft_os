"""services/test_learning_integration.py — AgentPlatform.run() records a trace (Wave 12).

Integration between Wave 11 (AgentPlatform) and Wave 12 (ILearningStore).
Reuses the same mock shape as test_agent_platform.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_agent_platform import AgentStatus
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from services.agent_platform import AgentPlatform

from adapters.in_memory_learning_store import InMemoryLearningStore
from adapters.in_memory_memory_store import InMemoryMemoryStore
from contracts.i_learning import ExecutionTrace


class _Planner(IPlanner):
    def plan(self, goal, context=None):
        return [Step(id="s1_a", task=f"analyze: {goal}"),
                Step(id="s1_b", task=f"execute: {goal}")]


class _Executor(IExecutor):
    def execute(self, workflow, router):
        plan = []
        for s in workflow.plan:
            r = router(ModelQuery(prompt=s.task))
            plan.append(s.with_result(
                output=r.text or "done",
                route_used=r.actual_model or "phi4",
                reflection_score=0.9,
                status=StepStatus.DONE,
            ))
        return workflow.with_plan(plan).with_status(WorkflowStatus.DONE)


def _router(model="phi4", text="done"):
    def r(q: ModelQuery) -> LlmResponse:
        return LlmResponse(text=text, actual_model=model)
    return r


def test_run_without_learning_store_does_not_break():
    p = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router())
    res = p.run("reasoning task: solve puzzle")
    assert res.status == AgentStatus.DONE


def test_run_records_trace_when_store_injected():
    store = InMemoryLearningStore(InMemoryMemoryStore())
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(model="phi4"),
        learning_store=store,
    )
    res = p.run("reasoning task: solve puzzle")
    assert res.status == AgentStatus.DONE

    traces = store.query("reasoning")
    assert len(traces) == 1
    t = traces[0]
    assert isinstance(t, ExecutionTrace)
    assert t.goal == "reasoning task: solve puzzle"
    assert t.final_status == "done"
    assert len(t.steps) == 2
    assert t.steps[0].model_id == "phi4"          # actual_model recorded
    assert t.steps[0].eval_score == 0.9           # reflection_score surfaced


def test_trace_queryable_by_pattern():
    store = InMemoryLearningStore(InMemoryMemoryStore())
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(model="gpt"),
        learning_store=store,
    )
    p.run("code generation: write a parser")
    found = store.query("generation")
    assert len(found) == 1
    assert found[0].steps[0].model_id == "gpt"


def test_multiple_runs_accumulate():
    store = InMemoryLearningStore(InMemoryMemoryStore())
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(model="phi4"),
        learning_store=store,
    )
    p.run("reasoning task A")
    p.run("reasoning task B")
    assert len(store.query("")) == 2
    assert "phi4" in store.aggregate("avg_eval_score", "model_id")
