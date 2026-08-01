"""(services) WorkflowExecutor — IExecutor orchestrator (Wave 10, ADR-013 Phase D/E).

Runs a workflow's plan sequentially (v0.1 — no DAG yet) by calling `router` for
each step, enriching the query with Memory (Wave 9) context, reflecting on the
output via Evaluation (Wave 7), and retrying through a different route when the
reflection rejects.

Boundaries (LAW 2):
- this module imports ONLY contracts.* (no adapters/, no sibling services/);
- `Reflection` and `RetryManager` are INJECTED as `IReflection`/`IRetryManager`,
  because `test_services_do_not_cross_import` forbids `from services.X import ...`.

The Workflow is immutable: the executor returns a brand NEW workflow object and
never mutates the one handed to it — that is what makes replay/reproduction a
matter of equality rather than hope.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from contracts.i_llm import ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import (
    IExecutor,
    IPlanner,
    RouterFn,
    Step,
    StepStatus,
    Workflow,
    WorkflowStatus,
)

# --- wiring types -----------------------------------------------------------
PlannerFn = Callable[[str, PolicyContext], List[Step]]
ReflectFn = Callable[[Step], bool]
RetryDecideFn = Callable[[Step], bool]
RetryPrepFn = Callable[[ModelQuery, PolicyContext, int], Tuple[ModelQuery, PolicyContext]]


class WorkflowExecutor(IExecutor):
    """Sequential step orchestrator.

    Args:
        memory: optional MemoryPlatform (Wave 9). When present, each step's
            ModelQuery is augmented with the session context. The executor knows
            ONLY the structural `SessionMemory` shape it calls — `augment_query`.
        reflection: IReflection (defaults to StepReflection in composition root).
        retry: IRetryManager (defaults to RetryManager in composition root).
        session_id: where to stash context in Memory; "wf:<workflow_id>" by default.
        context_window: last N turns fed into the step prompt.
    """

    def __init__(
        self,
        memory: object = None,
        reflection: Optional[IReflection] = None,
        retry: Optional[IRetryManager] = None,
        session_id: Optional[str] = None,
        context_window: int = 3,
    ) -> None:
        self._memory = memory
        self._reflection = reflection
        self._retry = retry
        self._session_id = session_id
        self._context_window = context_window

    # --- IExecutor ---------------------------------------------------------
    def execute(self, workflow: Workflow, router: RouterFn) -> Workflow:
        """Execute every pending step in order; return a NEW workflow."""
        if workflow.status == WorkflowStatus.DONE:
            return workflow

        wf = workflow.with_status(WorkflowStatus.RUNNING)
        # ensure all steps start from a clean pending state before running
        wf = wf.with_plan([s.with_status(StepStatus.PENDING) for s in wf.plan])

        for idx, step in enumerate(wf.plan):
            wf = self._run_step(wf, idx, step, router)
            if wf.status == WorkflowStatus.FAILED:
                return wf

        status = WorkflowStatus.DONE if wf.is_complete else WorkflowStatus.FAILED
        return wf.with_status(status)

    # --- step loop ---------------------------------------------------------
    def _run_step(
        self,
        wf: Workflow,
        idx: int,
        step: Step,
        router: RouterFn,
    ) -> Workflow:
        """Repeatedly attempt `step` through router until accepted or exhausted."""
        reflected = self._reflection
        retrier = self._retry

        running = wf.with_step(idx, step.with_status(StepStatus.RUNNING))
        wf = running.with_log(f"step '{step.id}': start")

        prompt = self._build_prompt(wf, step)
        query = ModelQuery(prompt=prompt, json_mode=True)
        context = PolicyContext(query=query, session_id=self._session_id or f"wf:{wf.id}")

        attempt = 0
        while True:
            attempt += 1
            attempt_step = running.plan[idx].with_attempt()
            running = running.with_step(idx, attempt_step)

            response = router(query)
            route = getattr(response, "actual_model", "") or ""

            if not response.ok():
                # transport/policy failure — decide whether to retry
                failed = attempt_step.with_result(
                    output="",
                    route_used=route,
                    status=StepStatus.FAILED,
                    error=response.error or "router failure",
                )
                running = running.with_step(idx, failed)
                wf = running
                if retrier is not None and retrier.should_retry(failed):
                    query, context = retrier.prepare_retry(query, context, attempt)
                    wf = wf.with_log(retrier.explain(attempt))
                    continue
                return self._fail(wf, idx, failed, reflected)

            out = response.text or ""
            scored = attempt_step.with_result(
                output=out,
                route_used=route,
                reflection_score=self._score(attempt_step, out),
                status=StepStatus.DONE,
            )
            accepted = reflected.evaluate_step(scored) if reflected else bool(out.strip())

            if accepted:
                running = running.with_step(idx, scored)
                running = running.with_log(
                    f"step '{step.id}': done (route={route}, score={scored.reflection_score:.2f})"
                )
                return running

            # reflection rejected the output
            rejected = scored.with_status(StepStatus.FAILED)
            running = running.with_step(idx, rejected)
            wf = running
            if retrier is not None and retrier.should_retry(rejected):
                query, context = retrier.prepare_retry(query, context, attempt)
                wf = wf.with_log(
                    f"step '{step.id}': reflection rejected (score={scored.reflection_score:.2f}) "
                    + retrier.explain(attempt)
                )
                continue
            return self._fail(wf, idx, rejected, reflected)

    # --- helpers -----------------------------------------------------------
    def _score(self, step: Step, output: str) -> float:
        if self._reflection is None:
            return 1.0 if output.strip() else 0.0
        return self._reflection.score(step.with_result(output=output))

    def _fail(self, wf: Workflow, idx: int, step: Step, reflected) -> Workflow:
        reason = step.error or "reflection rejected"
        return wf.with_step(idx, step).with_status(WorkflowStatus.FAILED).with_log(
            f"step '{step.id}': FAILED ({reason})"
        )

    def _build_prompt(self, wf: Workflow, step: Step) -> str:
        """Compose the step prompt from goal + variables + memory context."""
        parts: List[str] = []
        if wf.variables:
            kv = ", ".join(f"{k}={v}" for k, v in wf.variables.items())
            parts.append(f"[context] {kv}")
        if self._memory is not None and self._session_id:
            try:
                ctx = self._memory.build_context(self._session_id, limit=self._context_window)
                if ctx:
                    parts.append(f"[memory]\n{ctx}")
            except Exception:
                # memory is a best-effort enrichment, never a hard dependency
                pass
        parts.append(f"Goal: {wf.goal}")
        parts.append(f"Task: {step.task}")
        return "\n\n".join(parts)

    def _remember(self, wf: Workflow, step: Step, output: str) -> None:
        try:
            self._memory.remember_turn(
                self._session_id or f"wf:{wf.id}",
                output,
                role="assistant",
                tags=[MemoryKind := "workflow", str(wf.goal)],
                metadata={"step_id": step.id},
            )
        except Exception:
            # persistence is a side effect; never fail a run because of it
            pass
