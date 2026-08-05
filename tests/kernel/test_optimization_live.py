"""services/test_optimization_live.py — real optimizer path (gated).

Gated by OPTIMIZATION_LIVE=1. No external LLM: the router is a local stub.
Exercises Wave 11 -> Wave 12 patterns -> Wave 13 optimizer end to end.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIVE = os.environ.get("OPTIMIZATION_LIVE", "0") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set OPTIMIZATION_LIVE=1 to run live optimization path")

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import IExecutor, IPlanner, Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_learning import Pattern
from services.agent_platform import AgentPlatform
from services.pattern_based_optimizer import PatternBasedOptimizer

from contracts.i_optimization import Recommendation


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


def test_live_optimizer_generates_rec_from_pattern() -> None:
    patterns = [Pattern(description="phi4 beats gpt", confidence=0.92,
                        applies_to=("reasoning", "phi4"), recommendation="Prefer phi4 for reasoning tasks")]
    opt = PatternBasedOptimizer()
    recs = opt.recommend(patterns, {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}})
    assert len(recs) == 1
    assert recs[0].confidence == 0.92

    # full platform with optimizer
    p = AgentPlatform(planner=_Planner(), executor=_Executor(), router=_router(), optimizer=opt)
    res = p.run("reasoning task: solve")
    assert res.status == "done"
    assert len(res.optimization_recommendations) >= 1
