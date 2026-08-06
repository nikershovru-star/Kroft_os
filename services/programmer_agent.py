"""Programmer Agent — coding-specialised agent behaviour (Agents v0.1+, ADR-102).

K5/K6-compliant: services/ imports ONLY contracts.* + stdlib (same seam as ResearchAgent/
ArchitectAgent). Reuses the EXACT proven pattern — no new port, no new layer. Focus:
coding / implementation queries resolved against the live knowledge graph.

Behaviour:
    Goal -> Orchestrator.dispatch(capability="coding") -> ProgrammerAgent.run ->
    ReferenceSearchService (live graph) -> LLM (if wired) -> AgentResult

Graceful degradation (O1/I-09): without LLM it returns the matched graph hits verbatim.
"""

from __future__ import annotations

import uuid
from typing import Optional

from contracts.i_agent_executor import IAgentExecutor
from contracts.i_agent_platform import AgentResult, AgentStatus, IAgentPlatform
from contracts.i_knowledge_engine import IKnowledgeEngine
from contracts.i_llm import ILlm, ModelQuery
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_search import ISearchService
from contracts.i_workflow import Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_policy import PolicyContext


class ProgrammerAgent(IAgentPlatform):
    """Coding-specialised agent: retrieves implementation/code material and answers."""

    def __init__(
        self,
        search: ISearchService,
        knowledge: Optional[IKnowledgeEngine] = None,
        llm: Optional[ILlm] = None,
        top_k: int = 5,
    ) -> None:
        self._search = search
        self._knowledge = knowledge
        self._llm = llm
        self._top_k = top_k

    # --- IAgentPlatform ---------------------------------------------------
    def run(self, goal: str, context: Optional[PolicyContext] = None) -> AgentResult:
        plan = (Step(id="programmer", task=goal, status=StepStatus.PENDING),)
        wf = Workflow(
            id=f"programmer:{uuid.uuid4().hex[:8]}", goal=goal, plan=plan,
            status=WorkflowStatus.RUNNING,
        )
        result = AgentResult(goal=goal, workflow=wf)

        hits = self._search.search(goal, top_k=self._top_k)
        result = result.with_knowledge(*(h.source for h in hits))

        if self._llm is not None and hits:
            context_blob = "\n".join(f"- {h.source}: {h.content[:200]}" for h in hits)
            try:
                synthesis = self._llm.complete(
                    ModelQuery(prompt=f"As a senior programmer, answer concisely with code/pseudocode.\n"
                           f"Question: {goal}\n\nReference material:\n{context_blob}\n\nAnswer:")
                ).text
                result = result.with_tools(synthesis)
            except Exception:
                result = result.with_tools(
                    "\n".join(f"{h.source}: {h.content[:120]}" for h in hits)
                )
        else:
            if hits:
                result = result.with_tools(
                    "\n".join(f"{h.source}: {h.content[:120]}" for h in hits)
                )
            else:
                result = result.with_tools("no coding matches in the knowledge graph")

        return result.with_status(AgentStatus.DONE)

    def ask(self, goal: str, context: Optional[PolicyContext] = None) -> str:
        result = self.run(goal, context)
        if result.tool_results:
            return result.tool_results[-1]
        if result.error:
            return f"[programmer failed] {result.error}"
        return f"[programmer done] {result.status}"


class ProgrammerAgentExecutor(IAgentExecutor):
    """Bridge ProgrammerAgent into the Orchestrator's agent dispatch path."""

    def __init__(self, agent: ProgrammerAgent) -> None:
        self._agent = agent
        self.capability = "coding"

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        try:
            goal_text = str(goal.payload if goal.payload is not None else goal.capability)
            result = self._agent.run(goal_text)
            detail = result.tool_results[-1] if result.tool_results else result.status
            return TaskOutcome(success=result.is_success, detail=detail)
        except Exception as exc:  # noqa: BLE001
            return TaskOutcome(
                success=False, detail=f"programmer agent failed: {type(exc).__name__}: {exc}"
            )

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return goal.capability == "coding"
