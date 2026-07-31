"""services/test_autonomy_integration.py — AgentPlatform + autonomy (Wave 14).

Integration between Wave 11 (AgentPlatform), Wave 12 (Learning), and Wave 14
(autonomy). Reuses the mock shape from test_agent_platform.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_learning import ExecutionTrace
from contracts.i_autonomy import EvaluationReport, IAutonomyController, ISelfEvaluator
from contracts.i_optimization import Recommendation
from services.agent_platform import AgentPlatform
from services.threshold_autonomy_controller import ThresholdAutonomyController
from services.simple_self_evaluator import SimpleSelfEvaluator
from adapters.in_memory_learning_store import InMemoryLearningStore
from adapters.in_memory_memory_store import InMemoryMemoryStore

os.environ.setdefault("AUTONOMY_LIVE", "0")


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


def _store_with_traces(n=3):
    store = InMemoryLearningStore(InMemoryMemoryStore())
    for i in range(n):
        store.record(ExecutionTrace(trace_id=f"t{i}", goal="reasoning task", workflow_id="w",
            steps=(StepTraceOK(),), final_status="done", timestamp=float(i)))
    return store


def StepTraceOK():
    from contracts.i_learning import StepTrace
    return StepTrace(step_id="s", model_id="phi4", prompt="p", output="o", eval_score=0.9)


def test_run_without_autonomy_unchanged() -> None:
    p = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router())
    res = p.run("plain goal")
    assert res.status == "done"
    assert res.autonomy_log == ()


def test_run_with_autonomy_writes_report_observe_only() -> None:
    store = _store_with_traces(3)
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(),
        learning_store=store,
        autonomy_controller=_AlwaysRetrospect(),
        self_evaluator=SimpleSelfEvaluator(),
    )
    res = p.run("reasoning task")
    assert res.status == "done"
    assert len(res.autonomy_log) == 1
    rep = res.autonomy_log[0]
    assert isinstance(rep, EvaluationReport)
    assert rep.plan_success_rate == 1.0  # all 3 traces done
    # observe-only: no mutation of runtime happened


def test_autonomy_skipped_without_learning_store() -> None:
    # autonomy_controller present but no learning_store -> retrospective skipped
    p = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(),
        autonomy_controller=_AlwaysRetrospect(),
        self_evaluator=SimpleSelfEvaluator(),
    )
    res = p.run("reasoning task")
    assert res.autonomy_log == ()


def test_autonomy_does_not_change_run_behavior() -> None:
    base = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router())
    store = _store_with_traces(3)
    opt = AgentPlatform(
        planner=_Planner(), executor=_Executor(), router=_router(),
        learning_store=store,
        autonomy_controller=_AlwaysRetrospect(),
        self_evaluator=SimpleSelfEvaluator(),
    )
    r1 = base.run("reasoning task")
    r2 = opt.run("reasoning task")
    assert [s.status for s in r1.workflow.plan] == [s.status for s in r2.workflow.plan]
