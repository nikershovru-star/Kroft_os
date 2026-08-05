"""(tests) Wave 10 (ADR-013) Phase G — WorkflowExecutor with mocks.

Uses a fake router (callable port) + injected reflection/retry. No real LLM.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_workflow import (
    IReflection,
    IRetryManager,
    Step,
    StepStatus,
    Workflow,
    WorkflowStatus,
)
from services.reflection import StepReflection
from services.retry_manager import RetryManager
from services.workflow_executor import WorkflowExecutor
from adapters.rule_based_planner import RuleBasedPlanner


class _FixedReflection(IReflection):
    def __init__(self, accept: bool):
        self.accept = accept
        self.last_score = 0.0

    def score(self, step, scorecard=None):
        self.last_score = 1.0 if step.output.strip() else 0.0
        return self.last_score

    def evaluate_step(self, step, scorecard=None):
        return self.accept and bool(step.output.strip())


class _RecordingRetry(IRetryManager):
    """Records whether a retry was offered and always declines after the first."""

    def __init__(self):
        self.calls = 0

    def should_retry(self, step):
        # allow exactly one retry, then give up
        return step.attempts < 2

    def prepare_retry(self, query, context, attempt):
        self.calls += 1
        return query, context

    def explain(self, attempt):
        return f"attempt {attempt}: recorded retry (mock)"


def _router_factory(responses):
    """responses: list[LlmResponse]; consumed in order, cycled if exhausted."""
    seq = list(responses)
    idx = {"n": 0}

    def router(q: ModelQuery) -> LlmResponse:
        r = seq[idx["n"] % len(seq)]
        idx["n"] += 1
        return r

    return router


def _wf(goal="explain why X", tasks=("analyze", "execute", "validate")):
    plan = [Step(id=f"s{n}_{t}", task=f"{t}: {goal}") for n, t in enumerate(tasks, 1)]
    return Workflow(id="w1", goal=goal, plan=plan)


def test_executor_runs_two_steps_successfully():
    router = _router_factory([LlmResponse(text="result one is long enough"), LlmResponse(text="result two is long enough")])
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(), router)
    assert out.status == WorkflowStatus.DONE
    assert [s.status for s in out.plan] == [StepStatus.DONE, StepStatus.DONE, StepStatus.DONE]
    assert out.plan[0].output == "result one is long enough"
    assert out.plan[0].route_used == ""  # mock has no actual_model


def test_executor_records_route_used():
    resp = LlmResponse(text="ok this answer is definitely long enough")
    resp.actual_model = "phi4"
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(tasks=("analyze",)), _router_factory([resp]))
    assert out.plan[0].route_used == "phi4"


def test_original_workflow_is_untouched():
    wf = _wf()
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    ex.execute(wf, _router_factory([LlmResponse(text="x is long enough")]))
    assert wf.status == WorkflowStatus.DRAFT  # caller's object unchanged


def test_reflection_rejection_triggers_retry_then_fail():
    router = _router_factory([
        LlmResponse(text=""),     # attempt 1: empty -> rejected
        LlmResponse(text=""),     # attempt 2: still empty -> exhausted
    ])
    retry = _RecordingRetry()
    ex = WorkflowExecutor(reflection=StepReflection(), retry=retry)
    out = ex.execute(_wf(tasks=("analyze",)), router)
    assert out.status == WorkflowStatus.FAILED
    assert out.plan[0].status == StepStatus.FAILED
    assert out.plan[0].attempts == 2
    assert retry.calls == 1  # one retry was prepared


def test_reflection_rejection_then_success_on_retry():
    router = _router_factory([
        LlmResponse(text=""),            # attempt 1 rejected
        LlmResponse(text="a real answer here that passes the length check"),  # attempt 2 accepted
    ])
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(tasks=("analyze",)), router)
    assert out.status == WorkflowStatus.DONE
    assert out.plan[0].attempts == 2
    assert "a real answer" in out.plan[0].output


def test_router_error_is_treated_as_failure_and_retried():
    router = _router_factory([
        LlmResponse(text="", error="policy veto"),
        LlmResponse(text="recovered output long enough"),
    ])
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(tasks=("analyze",)), router)
    assert out.status == WorkflowStatus.DONE
    assert out.plan[0].error == ""


def test_reflection_log_is_explanatory():
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(), _router_factory([
        LlmResponse(text="answer one long enough"),
        LlmResponse(text="answer two long enough"),
    ]))
    log = "\n".join(out.reflection_log)
    assert "step 's1_analyze': done" in log
    assert "step 's3_validate': done" in log


def test_serialized_after_run_is_reproducible():
    import json
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    out = ex.execute(_wf(), _router_factory([LlmResponse(text="a"), LlmResponse(text="b")]))
    a = json.loads(out.to_json())
    b = json.loads(Workflow.from_json(out.to_json()).to_json())
    assert a == b


def test_full_pipeline_with_real_planner():
    plan = RuleBasedPlanner().plan("Explain why the build failed", None)
    wf = Workflow(id="w1", goal="Explain why the build failed", plan=plan)
    ex = WorkflowExecutor(reflection=StepReflection(), retry=RetryManager())
    router = _router_factory([
        LlmResponse(text="context gathered here"),
        LlmResponse(text="the explanation is a timeout"),
        LlmResponse(text="fact-checked and consistent"),
    ])
    out = ex.execute(wf, router)
    assert out.status == WorkflowStatus.DONE
    assert len(out.plan) == 3
    assert all(s.status == StepStatus.DONE for s in out.plan)
