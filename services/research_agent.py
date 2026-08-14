"""Research Agent — first concrete agent behaviour (Agents v0.1, ADR-102).

K5/K6-compliant: services/ imports ONLY contracts.* + stdlib. The agent receives its
domain services (search / knowledge / llm) as INJECTED ports (ISearchService,
IKnowledgeEngine, ILlm) — never the concrete services — so this module stays axis-clean.

Behaviour (ТЗ-AGENT-BEHAVIOUR-01, ADR-102):
    Goal -> Orchestrator.dispatch -> ResearchAgent.run -> KnowledgeEngine ->
    ReferenceSearchService -> LLM (if wired) -> AgentResult

The agent REALLY uses ReferenceSearchService over the live knowledge graph (the ingested
vault) — it does NOT return a fixed answer. LLM-free by default (I-09): without an llm_client
it returns the matched graph hits (graceful degradation, O1). With an llm_client it
synthesises a short answer over the hits.

`ResearchAgent` implements IAgentPlatform (ADR-014) so it slots into the existing agent
platform seam. `ResearchAgentExecutor` implements IAgentExecutor (ADR-080) so the
Orchestrator.dispatch agent-path can drive it and evolve trust from the real outcome.
"""

from __future__ import annotations

import uuid
from typing import Optional, Tuple

from contracts.i_agent_executor import IAgentExecutor
from contracts.i_agent_platform import AgentResult, AgentStatus, IAgentPlatform
from contracts.i_knowledge_engine import IKnowledgeEngine
from contracts.i_llm import ILlm, ModelQuery
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_search import ISearchService
from contracts.i_workflow import Step, StepStatus, Workflow, WorkflowStatus
from contracts.i_policy import PolicyContext


class ResearchAgent(IAgentPlatform):
    """Research-specialised agent: retrieves from the live knowledge graph and answers.

    Args:
        search: ISearchService (injected) — e.g. ReferenceSearchService(memory, graph).
        knowledge: optional IKnowledgeEngine (injected) — reserved for on-demand enrichment.
        llm: optional ILlm (injected) — advisory synthesis over the retrieved hits.
        top_k: how many search hits to surface / feed to the LLM.
    """

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
        # Deterministic workflow shell; the agent's value is in knowledge_hits + tool_results.
        plan = (Step(id="research", task=goal, status=StepStatus.PENDING),)
        wf = Workflow(
            id=f"research:{uuid.uuid4().hex[:8]}", goal=goal, plan=plan,
            status=WorkflowStatus.RUNNING,
        )
        result = AgentResult(goal=goal, workflow=wf)

        # 1. REAL retrieval over the live knowledge graph (ТЗ-SEARCH-01 / ТЗ-KNOWLEDGE-ENGINE-01).
        hits = self._search.search(goal, top_k=self._top_k)
        hit_sources = tuple(h.source for h in hits)
        result = result.with_knowledge(*hit_sources)

        # 2. Synthesise an answer (graceful degradation, O1):
        #    - LLM wired + we have hits -> ask the model to summarise over the hits.
        #    - otherwise -> return the matched hits verbatim (LLM-free, deterministic, I-09).
        if self._llm is not None and hits:
            context_blob = "\n".join(
                f"- {h.source}: {h.content[:200]}" for h in hits
            )
            try:
                synthesis = self._llm.complete(
                    ModelQuery(prompt=f"Question: {goal}\n\nKnowledge:\n{context_blob}\n\nAnswer concisely:")
                ).text
                result = result.with_tools(synthesis)
            except Exception:
                # model failure must not break the run — fall back to raw hits (O1).
                result = result.with_tools(
                    "\n".join(f"{h.source}: {h.content[:120]}" for h in hits)
                )
        else:
            if hits:
                result = result.with_tools(
                    "\n".join(f"{h.source}: {h.content[:120]}" for h in hits)
                )
            else:
                # Stage 4: signal a knowledge gap instead of a silent "no matches".
                # The agent does NOT auto-ingest here (that is S4.4, gated by config);
                # it surfaces the gap so an upstream planner / autonomous loop can act.
                result = result.with_gap(True).with_tools(
                    "KNOWLEDGE_GAP: no matches in the knowledge graph for this query"
                )

        result = result.with_status(AgentStatus.DONE)
        return result

    def ask(self, goal: str, context: Optional[PolicyContext] = None) -> str:
        """Convenience one-shot: run the goal and return the textual answer only."""
        result = self.run(goal, context)
        if result.tool_results:
            return result.tool_results[-1]
        if result.error:
            return f"[research failed] {result.error}"
        return f"[research done] {result.status}"


class ResearchAgentExecutor(IAgentExecutor):
    """Bridge ResearchAgent (IAgentPlatform) into the Orchestrator's agent dispatch path.

    The Orchestrator calls ``execute(goal)`` and expects a TaskOutcome; this executor runs
    the ResearchAgent and maps the frozen AgentResult -> TaskOutcome so trust evolves from the
    REAL outcome (success +, failure -), uniform with plugins/remote/skills (ТЗ-AGENT-EXEC-01).
    """

    def __init__(self, agent: ResearchAgent) -> None:
        self._agent = agent
        self.capability = "research"

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        try:
            goal_text = str(goal.payload if goal.payload is not None else goal.capability)
            result = self._agent.run(goal_text)
            detail = result.tool_results[-1] if result.tool_results else result.status
            return TaskOutcome(success=result.is_success, detail=detail)
        except Exception as exc:  # noqa: BLE001 — executor faults must lower trust, not crash
            return TaskOutcome(
                success=False, detail=f"research agent failed: {type(exc).__name__}: {exc}"
            )

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        # The orchestrator already routed by capability; this executor is research-scoped.
        return goal.capability == "research"
