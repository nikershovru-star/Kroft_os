"""(services) AgentPlatform — IAgentPlatform orchestrator (Wave 11, ADR-014).

Ties the pre-existing agent core (Stage 33: `IAgent` / `ToolRegistry`) to the
Wave 5-10 platforms into one traceable run. This is the "Platform" layer: a thin
coordinator over ports, not another monolith.

Boundaries (LAW 2):
- imports ONLY contracts.* — never adapters/ or sibling services/;
- every concrete subsystem (planner, executor, memory, knowledge, evaluator,
  policy engine, tools) is INJECTED via the constructor. The composition root
  (CLI/main) assembles them; this module never imports them.

`test_services_do_not_cross_import` is therefore satisfied by construction.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, List, Optional

from contracts.i_agent_platform import AgentResult, AgentStatus, IAgentPlatform
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import IExecutor, IPlanner, StepStatus, Workflow, WorkflowStatus

# structural router port (LAW 2): a callable, not the concrete Router
RouterFn = Callable[[ModelQuery], LlmResponse]

# tool handler: either a ToolRegistry-like object or an IАgent adapter
ToolHandler = Any


class AgentPlatform(IAgentPlatform):
    """Coordinate Planner + Memory + Knowledge + Tools + Workflow + Policies + LLM + Evaluator.

    Args:
        planner: IPlanner (Wave 10 RuleBasedPlanner).
        executor: IExecutor (Wave 10 WorkflowExecutor).
        router: callable port used by the executor to reach models (Wave 6).
        memory: optional MemoryPlatform (Wave 9). When present, the goal and the
            workflow outcome are persisted to Session + Long-Term memory.
        knowledge: optional KnowledgePlatform (Wave 8). When present, the goal is
            used as a retrieval query and matched facts are attached to the result.
        evaluator: optional EvaluationPlatform (Wave 7). When present and a
            Scorecard is produced, its metrics are summarised in the result.
        tools: optional tool handler (Stage 33 ToolRegistry / IАgent adapter). When
            present, goal-shaped tool intents are delegated to it.
        policy_engine: optional PolicyEngine (Wave 5) — consulted only for route
            logging; routing itself happens inside `router`.
        session_id: where agent memory is filed ("agent:<run>" by default).
    """

    def __init__(
        self,
        planner: IPlanner,
        executor: IExecutor,
        router: RouterFn,
        memory: object = None,
        knowledge: object = None,
        evaluator: object = None,
        tools: ToolHandler = None,
        policy_engine: object = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._router = router
        self._memory = memory
        self._knowledge = knowledge
        self._evaluator = evaluator
        self._tools = tools
        self._engine = policy_engine
        self._session_id = session_id or f"agent:{uuid.uuid4().hex[:8]}"

    # --- IAgentPlatform ---------------------------------------------------
    def run(self, goal: str, context: Optional[PolicyContext] = None) -> AgentResult:
        ctx = context or PolicyContext(query=ModelQuery(prompt=goal))

        # 1. Plan via Wave 10 planner -> List[Step]
        plan = self._planner.plan(goal, ctx)
        wf = Workflow(id=self._session_id, goal=goal, plan=tuple(plan))
        result = AgentResult(goal=goal, workflow=wf)

        # 2. Knowledge: optional retrieval by goal (Wave 8)
        if self._knowledge is not None:
            result = self._consult_knowledge(result, goal)

        # 3. Execute the plan through the Workflow executor (Wave 10)
        try:
            wf = self._executor.execute(wf, self._router)
        except Exception as exc:  # orchestration is resilient: never crash the run
            wf = wf.with_status(WorkflowStatus.FAILED)
            result = result.with_status(AgentStatus.FAILED, error=f"execution: {exc}")
            return self._finalize(result, wf)

        result = result.with_routes(*self._collect_routes(wf))
        status = AgentStatus.DONE if wf.status == WorkflowStatus.DONE else AgentStatus.FAILED
        result = result.with_status(status)
        if status == AgentStatus.FAILED and not result.error:
            # executor returned FAILED without raising — record it as execution failure
            result = result.with_status(status, error="execution: workflow did not complete")

        # 4. Memory: persist goal + outcome (Wave 9)
        if self._memory is not None:
            result = self._persist_memory(result, goal, wf)

        # 5. Evaluation: optional measurement (Wave 7)
        if self._evaluator is not None:
            result = self._measure(result, goal, wf)

        # 6. Tools: optional delegation (Stage 33)
        if self._tools is not None:
            result = self._delegate_tools(result, goal)

        return self._finalize(result, wf)

    # --- subsystem integrations ------------------------------------------
    def _consult_knowledge(self, result: AgentResult, goal: str) -> AgentResult:
        try:
            facts = self._knowledge.find(goal, limit=5)
            hits = tuple(str(getattr(f, "subject", f)) for f in (facts or []))
            return result.with_knowledge(*hits)
        except Exception:
            return result  # best-effort enrichment

    def _collect_routes(self, wf: Workflow) -> List[str]:
        return [f"{s.id}->{s.route_used}" for s in wf.plan if s.route_used]

    def _persist_memory(self, result: AgentResult, goal: str, wf: Workflow) -> AgentResult:
        try:
            self._memory.remember_turn(self._session_id, f"goal: {goal}", role="user")
            summary = "; ".join(f"{s.id}={s.status}" for s in wf.plan)
            item = self._memory.remember_turn(
                self._session_id, f"outcome: {summary}", role="assistant", importance=0.8,
            )
            return result.with_memory(item.key)
        except Exception:
            return result

    def _measure(self, result: AgentResult, goal: str, wf: Workflow) -> AgentResult:
        try:
            from contracts.i_eval import Task, TaskCategory

            task = Task(id=f"{self._session_id}:goal", category=TaskCategory.REASONING, input=goal)
            scorecard = self._evaluator.run(task, self._router)
            lines = tuple(f"{k}={v:.2f}" for k, v in (scorecard.metrics or {}).items())
            return result.with_eval(*lines)
        except Exception:
            return result

    def _delegate_tools(self, result: AgentResult, goal: str) -> AgentResult:
        try:
            if hasattr(self._tools, "execute"):
                out = self._tools.execute(goal)
                return result.with_tools(self._render_tool_out(out))
            if hasattr(self._tools, "list_tools"):
                names = [t.name for t in self._tools.list_tools()]
                return result.with_tools(f"tools available: {', '.join(names)}")
        except Exception:
            pass
        return result

    @staticmethod
    def _render_tool_out(out: Any) -> str:
        if isinstance(out, dict):
            ok = out.get("ok", out.get("success", True))
            if not ok:
                return f"tool error: {out.get('error', 'unknown')}"
            plan = out.get("plan") or out.get("results")
            return f"tool ok: {plan}"
        return f"tool: {out}"

    def _finalize(self, result: AgentResult, wf: Workflow) -> AgentResult:
        # attach the (possibly failed) workflow to the result for full traceability
        return result.__class__(**{**result.__dict__, "workflow": wf})
