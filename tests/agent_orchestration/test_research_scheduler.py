"""P1-D proof-of-fire: AutonomousResearchScheduler (L8, ADR-0XX).

Self-contained — NO Ollama, NO network. Fake IAgentPlatform proves the
scheduler self-sets goals, accrues findings, and degrades gracefully.

Proves:
  - seed of 2 goals + max_generated -> run_for(3) yields 3 findings, all success
  - findings() accumulates across calls
  - empty seed + max_generated=0 -> run_for(5) yields [] (no self-set goals possible)
  - agent=None -> TypeError (contract requires instance)
  - determinism: same scheduler state -> same finding count
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from contracts.i_agent_platform import (
    AgentResult,
    AgentStatus,
    IAgentPlatform,
    ResearchFinding,
)
from contracts.i_workflow import Workflow, Step, StepStatus, WorkflowStatus
from services.research_scheduler import AutonomousResearchScheduler


def _mk_result(goal: str, success: bool = True, hits=("src:A", "src:B")):
    wf = Workflow(id="w", goal=goal, plan=(Step(id="s", task=goal, status=StepStatus.DONE),),
                  status=WorkflowStatus.DONE if success else WorkflowStatus.RUNNING)
    res = AgentResult(goal=goal, workflow=wf,
                      status=AgentStatus.DONE if success else AgentStatus.FAILED,
                      knowledge_hits=tuple(hits) if success else ())
    return res.with_tools(f"answer for {goal}")


class _FakeAgent(IAgentPlatform):
    def __init__(self, succeed: bool = True):
        self._ok = succeed
        self.calls: List[str] = []
    def run(self, goal: str, context=None) -> AgentResult:
        self.calls.append(goal)
        return _mk_result(goal, success=self._ok)
    def ask(self, goal: str, context=None) -> str:
        return self.run(goal).tool_results[-1]


def test_run_for_yields_findings_and_all_success():
    agent = _FakeAgent()
    sched = AutonomousResearchScheduler(agent, goal_seed=["g1", "g2"],
                                       max_generated_goals=2)
    out = sched.run_for(3)
    assert len(out) == 3
    assert all(f.success for f in out)
    assert out[0].goal == "g1" and out[1].goal == "g2"
    # 3rd goal was self-derived from g2's source hits
    assert out[2].goal.startswith("follow-up:")
    assert all(len(f.source_hits) == 2 for f in out)


def test_findings_accumulate():
    agent = _FakeAgent()
    sched = AutonomousResearchScheduler(agent, goal_seed=["a", "b"],
                                       max_generated_goals=0)
    sched.run_for(2)
    sched.run_for(1)  # no more seed/goals -> no-op
    findings = sched.findings()
    assert len(findings) == 2
    assert findings[0].goal == "a" and findings[1].goal == "b"


def test_empty_seed_no_generated_yields_nothing():
    agent = _FakeAgent()
    sched = AutonomousResearchScheduler(agent, goal_seed=[], max_generated_goals=0)
    out = sched.run_for(5)
    assert out == []
    assert sched.findings() == []


def test_none_agent_raises():
    with pytest.raises(TypeError):
        AutonomousResearchScheduler(None, goal_seed=["x"])


def test_determinism_same_count():
    a = AutonomousResearchScheduler(_FakeAgent(), goal_seed=["x", "y"],
                                    max_generated_goals=1)
    b = AutonomousResearchScheduler(_FakeAgent(), goal_seed=["x", "y"],
                                    max_generated_goals=1)
    assert len(a.run_for(2)) == len(b.run_for(2)) == 2
