"""services/test_learning_live.py — real AgentPlatform + LearningStore (gated).

Gated by LEARNING_LIVE=1. No external LLM call: the router is a local stub
returning actual_model, so this exercises the full Wave 11 -> Wave 12 path
(plan -> execute -> build trace -> persist -> query) without network.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIVE = os.environ.get("LEARNING_LIVE", "0") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set LEARNING_LIVE=1 to run live learning path")

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from services.agent_platform import AgentPlatform

from adapters.in_memory_learning_store import InMemoryLearningStore
from adapters.in_memory_memory_store import InMemoryMemoryStore
from contracts.i_learning import ExecutionTrace, ILearningStore, StepTrace


class _Planner(IPlanner):
    def plan(self, goal, context=None):
        return [Step(id="s_a", task=f"think: {goal}"),
                Step(id="s_b", task=f"act: {goal}"),
                Step(id="s_c", task=f"verify: {goal}")]


class _Executor(IExecutor):
    def execute(self, workflow, router):
        plan = []
        for s in workflow.plan:
            r = router(ModelQuery(prompt=s.task))
            plan.append(s.with_result(
                output=r.text or "ok",
                route_used=r.actual_model or "phi4",
                reflection_score=0.88,
                status=StepStatus.DONE,
            ))
        return workflow.with_plan(plan).with_status(WorkflowStatus.DONE)


def _router(model="phi4", text="ok"):
    def r(q: ModelQuery) -> LlmResponse:
        return LlmResponse(text=text, actual_model=model)
    return r


def test_live_run_records_trace_with_actual_model_and_eval():
    store = InMemoryLearningStore(InMemoryMemoryStore())
    assert isinstance(store, ILearningStore)
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(model="phi4"),
        learning_store=store,
    )
    res = p.run("reasoning task: deep analysis")
    assert res.status == "done"

    traces = store.query("reasoning")
    assert len(traces) == 1
    t: ExecutionTrace = traces[0]
    # trace is immutable and carries the real model + eval score
    assert t.steps[0].model_id == "phi4"
    assert t.steps[0].eval_score == 0.88
    assert all(isinstance(s, StepTrace) for s in t.steps)
    # aggregate works end-to-end
    avg = store.aggregate("avg_eval_score", "model_id")
    assert avg["phi4"] == 0.88
