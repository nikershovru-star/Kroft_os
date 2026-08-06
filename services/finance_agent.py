"""Finance Agent — finance-specialised agent behaviour (Agents v0.1+, ADR-102).

K5/K6-compliant: services/ imports ONLY contracts.* + stdlib (same seam as the other agents).
Reuses the EXACT proven pattern — no new port, no new layer. Focus: finance / trading /
market queries resolved against the live knowledge graph.

NOTE (ADR-102): a real exchange/trading adapter (moneygen IExchangeClient / MarketMind
ITradingStrategy) is an OUT-OF-SCOPE v0.1 extension wired as a separate K6 adapter. The v0.1
Finance Agent uses the same search+LLM seam as the other agents; the external market data
hook plugs in later without touching the kernel/orchestrator.

Behaviour:
    Goal -> Orchestrator.dispatch(capability="finance") -> FinanceAgent.run ->
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


class FinanceAgent(IAgentPlatform):
    """Finance-specialised agent: retrieves finance/market material and answers."""

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
        plan = (Step(id="finance", task=goal, status=StepStatus.PENDING),)
        wf = Workflow(
            id=f"finance:{uuid.uuid4().hex[:8]}", goal=goal, plan=plan,
            status=WorkflowStatus.RUNNING,
        )
        result = AgentResult(goal=goal, workflow=wf)

        hits = self._search.search(goal, top_k=self._top_k)
        result = result.with_knowledge(*(h.source for h in hits))

        if self._llm is not None and hits:
            context_blob = "\n".join(f"- {h.source}: {h.content[:200]}" for h in hits)
            try:
                synthesis = self._llm.complete(
                    ModelQuery(prompt=f"As a finance analyst, answer concisely with risk notes.\n"
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
                result = result.with_tools("no finance matches in the knowledge graph")

        return result.with_status(AgentStatus.DONE)

    def ask(self, goal: str, context: Optional[PolicyContext] = None) -> str:
        result = self.run(goal, context)
        if result.tool_results:
            return result.tool_results[-1]
        if result.error:
            return f"[finance failed] {result.error}"
        return f"[finance done] {result.status}"


class FinanceAgentExecutor(IAgentExecutor):
    """Bridge FinanceAgent into the Orchestrator's agent dispatch path."""

    def __init__(self, agent: FinanceAgent) -> None:
        self._agent = agent
        self.capability = "finance"

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        try:
            goal_text = str(goal.payload if goal.payload is not None else goal.capability)
            result = self._agent.run(goal_text)
            detail = result.tool_results[-1] if result.tool_results else result.status
            return TaskOutcome(success=result.is_success, detail=detail)
        except Exception as exc:  # noqa: BLE001
            return TaskOutcome(
                success=False, detail=f"finance agent failed: {type(exc).__name__}: {exc}"
            )

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return goal.capability == "finance"
