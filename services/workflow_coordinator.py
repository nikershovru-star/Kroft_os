"""WorkflowCoordinator — сборка Workflow из goal + исполнение через AgentRuntime (Wave C2).

K1/K6: services импортирует только contracts + stdlib. НЕ импортирует другие services
(StigmergyStrategy инжектится как ICoordinationStrategy из composition root).

Исполнение: каждый Step -> OrchestrationGoal(capability из variables["root_capability"])
-> IAgentRuntime.delegate_step (stigmergy blackboard-обмен). Возвращает НОВЫЙ Workflow
(copy-on-write, ADR-013), шаги помечаются DONE с output из TaskOutcome.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from contracts.i_agent_runtime import IAgentRuntime
from contracts.i_coordination_strategy import ICoordinationStrategy
from contracts.i_orchestrator import OrchestrationGoal
from contracts.i_workflow import Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_workflow_coordinator import IWorkflowCoordinator


class WorkflowCoordinator(IWorkflowCoordinator):
    """Строит Workflow из goal и исполняет через AgentRuntime (stigmergy)."""

    def __init__(
        self,
        runtime: IAgentRuntime,
        strategy: ICoordinationStrategy,
        root_capability: str = "research",
    ) -> None:
        self._runtime = runtime
        self._strategy = strategy
        self._root_capability = root_capability

    def build_workflow(self, goal: str) -> Workflow:
        # I-09: детерминированный id (sha256, НЕ hash())
        wf_id = f"wf:{hashlib.sha256(goal.encode('utf-8')).hexdigest()[:12]}"
        step = Step(id="s1", task=goal)
        return Workflow(
            id=wf_id,
            goal=goal,
            plan=(step,),
            variables={"root_capability": self._root_capability},
            status=WorkflowStatus.DRAFT,
        )

    def choose_strategy(self) -> ICoordinationStrategy:
        return self._strategy

    def run(self, workflow: Workflow) -> Workflow:
        capability = workflow.variables.get("root_capability", self._root_capability)
        wf = workflow.with_status(WorkflowStatus.RUNNING)
        updated_plan = []
        for step in wf.plan:
            child_goal = OrchestrationGoal(
                goal_id=step.id, capability=capability, payload=step.task
            )
            outcome = self._runtime.delegate_step(wf.id, child_goal)
            new_step = step.with_result(
                output=outcome.detail,
                route_used=capability,
                status=StepStatus.DONE if outcome.success else StepStatus.FAILED,
                error="" if outcome.success else outcome.detail,
            )
            updated_plan.append(new_step)
            if not outcome.success:
                wf = wf.with_plan(tuple(updated_plan)).with_status(WorkflowStatus.FAILED)
                return wf
        wf = wf.with_plan(tuple(updated_plan)).with_status(WorkflowStatus.DONE)
        return wf
