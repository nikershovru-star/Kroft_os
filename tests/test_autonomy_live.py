"""services/test_autonomy_live.py — real autonomy path (gated).

Gated by AUTONOMY_LIVE=1. No external LLM: stubs only. Exercises the full
Wave 11 -> Wave 12 traces -> Wave 14 retrospective path end to end.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIVE = os.environ.get("AUTONOMY_LIVE", "0") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set AUTONOMY_LIVE=1 to run live autonomy path")

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_learning import ExecutionTrace, StepTrace
from contracts.i_autonomy import EvaluationReport, IAutonomyController, ISelfEvaluator
from services.agent_platform import AgentPlatform
from services.threshold_autonomy_controller import ThresholdAutonomyController
from services.simple_self_evaluator import SimpleSelfEvaluator
from adapters.in_memory_learning_store import InMemoryLearningStore
from adapters.in_memory_memory_store import InMemoryMemoryStore


class _Planner(IPlanner):
    def plan(self, goal, context=None):
        return [Step(id="s1", task=f"t: {goal}"), Step(id="s2", task=f"e: {goal}")]


class _Executor(IExecutor):
    def execute(self, wf, router):
        plan = [s.with_result(output="ok", route_used=router(ModelQuery(prompt=s.task)).actual_model or "phi4",
                                reflection_score=0.9, status=StepStatus.DONE) for s in wf.plan]
        return wf.with_plan(plan).with_status(WorkflowStatus.DONE)


def _router(model="phi4"):
    def r(q: ModelQuery) -> LlmResponse:
        return LlmResponse(text="ok", actual_model=model)
    return r


class _AlwaysRetrospect(IAutonomyController):
    def should_retrospect(self, traces, config):
        return True


def test_live_autonomy_generates_report() -> None:
    store = InMemoryLearningStore(InMemoryMemoryStore())
    for i in range(3):
        store.record(ExecutionTrace(trace_id=f"t{i}", goal="reasoning task", workflow_id="w",
            steps=(StepTrace(step_id="s", model_id="phi4", prompt="p", output="o", eval_score=0.9),),
            final_status="done", timestamp=float(i)))
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(),
        learning_store=store,
        autonomy_controller=_AlwaysRetrospect(),
        self_evaluator=SimpleSelfEvaluator(),
    )
    res = p.run("reasoning task: solve")
    assert res.status == "done"
    assert len(res.autonomy_log) == 1
    assert isinstance(res.autonomy_log[0], EvaluationReport)
    assert res.autonomy_log[0].plan_success_rate == 1.0
