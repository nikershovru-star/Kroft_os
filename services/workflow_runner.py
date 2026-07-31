"""(services) workflow_runner — composition root for the Workflow Platform (Wave 10).

This is the ONE place that knows about the concrete `StepReflection` and
`RetryManager`. The orchestrator (`workflow_executor.py`) only depends on the
`IReflection` / `IRetryManager` ports, so it passes the service cross-import
gate. Wiring lives here, where sibling-service imports are legitimate.
"""
from __future__ import annotations

from typing import Optional

from contracts.i_workflow import IReflection, IRetryManager, Workflow, RouterFn
from services.reflection import StepReflection
from services.retry_manager import RetryManager
from services.workflow_executor import WorkflowExecutor


def build_executor(
    memory: object = None,
    reflection: Optional[IReflection] = None,
    retry: Optional[IRetryManager] = None,
    session_id: Optional[str] = None,
    context_window: int = 3,
) -> WorkflowExecutor:
    """Default wiring: real StepReflection + RetryManager unless overridden."""
    return WorkflowExecutor(
        memory=memory,
        reflection=reflection or StepReflection(),
        retry=retry or RetryManager(),
        session_id=session_id,
        context_window=context_window,
    )


def run_workflow(
    workflow: Workflow,
    router: RouterFn,
    memory: object = None,
    session_id: Optional[str] = None,
) -> Workflow:
    """One-shot: build the default executor and run the workflow."""
    return build_executor(memory=memory, session_id=session_id).execute(workflow, router)
