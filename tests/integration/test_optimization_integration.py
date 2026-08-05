"""services/test_optimization_integration.py — AgentPlatform + optimizer (Wave 13).

Integration between Wave 11 (AgentPlatform), Wave 12 (patterns), and Wave 13
(optimizer). Reuses the mock shape from test_agent_platform.py.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_learning import Pattern
from contracts.i_optimization import Recommendation
from services.agent_platform import AgentPlatform
from services.pattern_based_optimizer import PatternBasedOptimizer

os.environ.setdefault("OPTIMIZATION_LIVE", "0")


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


class _StaticOptimizer(PatternBasedOptimizer):
    """Returns a fixed rec regardless of input (so the test is deterministic)."""
    def recommend(self, patterns, current_config):
        return [Recommendation(id="rec:fixed", target="policy:x:w", value='{"quality": 0.7}',
                               rationale="test", confidence=0.9, source_pattern="fixed")]


def test_run_without_optimizer_unchanged() -> None:
    p = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router())
    res = p.run("plain goal")
    assert res.status == "done"
    assert res.optimization_recommendations == ()


def test_run_with_optimizer_records_rec_observe_only() -> None:
    p = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router(), optimizer=_StaticOptimizer())
    res = p.run("reasoning task")
    assert res.status == "done"
    assert len(res.optimization_recommendations) == 1
    rec = res.optimization_recommendations[0]
    assert rec.id == "rec:fixed"
    # observe-only: status stays proposed, nothing applied to runtime
    assert rec.status == "proposed"


def test_optimizer_does_not_change_run_behavior() -> None:
    # with vs without optimizer: same workflow outcome
    base = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router())
    opt = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router(), optimizer=_StaticOptimizer())
    r1 = base.run("reasoning task")
    r2 = opt.run("reasoning task")
    assert [s.status for s in r1.workflow.plan] == [s.status for s in r2.workflow.plan]
