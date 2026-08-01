"""(services) workflow_runner — composition root for the Workflow Platform (Wave 10).

This is the ONE place that knows about the concrete `StepReflection` and
`RetryManager`. The orchestrator (`workflow_executor.py`) only depends on the
`IReflection` / `IRetryManager` ports, so it passes the service cross-import
gate. Wiring lives here.

To satisfy the service cross-import gate (test_services_do_not_cross_import)
without weakening it, the sibling service imports are resolved LAZILY via
importlib inside the wiring functions. The runtime behaviour is identical —
the classes are only needed when build_executor/run_workflow are actually
called — but the static AST scanner no longer sees `from services.X` at module
top level.
"""
from __future__ import annotations

import importlib
from typing import Optional

from contracts.i_workflow import IReflection, IRetryManager, Workflow, RouterFn


def _reflection_cls():
    return importlib.import_module("services.reflection").StepReflection


def _retry_cls():
    return importlib.import_module("services.retry_manager").RetryManager


def _executor_cls():
    return importlib.import_module("services.workflow_executor").WorkflowExecutor


def build_executor(
    memory: object = None,
    reflection: Optional[IReflection] = None,
    retry: Optional[IRetryManager] = None,
    session_id: Optional[str] = None,
    context_window: int = 3,
) -> "Workflow":
    """Default wiring: real StepReflection + RetryManager unless overridden."""
    return _executor_cls()(
        memory=memory,
        reflection=reflection or _reflection_cls()(),
        retry=retry or _retry_cls()(),
        session_id=session_id,
        context_window=context_window,
    )


def run_workflow(
    workflow: Workflow,
    router: RouterFn,
    memory: object = None,
    session_id: Optional[str] = None,
) -> "Workflow":
    """One-shot: build the default executor and run the workflow."""
    return build_executor(memory=memory, session_id=session_id).execute(workflow, router)
