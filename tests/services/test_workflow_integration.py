"""(tests) Wave 10 (ADR-013) Phase G — integration:
RuleBasedPlanner + mock Router + PolicyEngine + Memory + StepReflection.

Offline (real PolicyEngine from Wave 5, mock ILlm adapter). Proves ADR-013 §2.4:
a Workflow is data end-to-end, the executor enriches the prompt with Session
Memory context, and reflection gates the result.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ILlm, LlmResponse, ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import Step, StepStatus, Workflow, WorkflowStatus
from adapters.rule_based_planner import RuleBasedPlanner
from services.workflow_executor import WorkflowExecutor
from services.workflow_runner import build_executor
from services.memory_platform import MemoryPlatform
from adapters.in_memory_memory_store import InMemoryMemoryStore
from policies.budget_policy import BudgetPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from contracts.model_registry import ModelRegistry


class _Model(ILlm):
    def __init__(self, info: ModelInfo, out: str):
        self._info = info
        self._out = out

    @property
    def model_info(self) -> ModelInfo:
        return self._info

    def complete(self, query: ModelQuery) -> LlmResponse:
        return LlmResponse(text=self._out, actual_model=self._info.id)

    def stream(self, query: ModelQuery):
        yield self._out

    async def acomplete(self, query):
        return self.complete(query)


def _registry_and_engine():
    reg = ModelRegistry()
    reg.register_model(ModelInfo(
        id="phi4", provider="ollama", local=True, free=True,
        reasoning=False, context_window=8000,
    ))
    reg.register_model(ModelInfo(
        id="gpt-mini", provider="openai", local=False, free=False,
        reasoning=True, context_window=32000,
    ))
    engine = PolicyEngine(reg)
    engine.register(BudgetPolicy())
    engine.register(ProviderSelectionPolicy())
    return reg, engine


def _router_from_engine(engine, reg):
    from adapters.router import Router
    adapters = {
        "ollama": _Model(reg.catalog()[0], ""),
        "openai": _Model(reg.catalog()[1], ""),
    }
    # build a router that produces a step-shaped answer
    def router(q: ModelQuery) -> LlmResponse:
        # capture the prompt so tests can assert Memory enrichment
        router.last_prompt = q.prompt
        decision = engine.decide(PolicyContext(query=q))
        if not decision.allowed:
            return LlmResponse(text="", error="veto")
        info = decision.selected_model
        # produce an answer long enough to pass reflection
        return LlmResponse(text=f"Answer about {q.prompt[-30:]} with sufficient detail.", actual_model=info.id)
    router.last_prompt = ""
    return router


def test_planner_router_memory_pipeline():
    reg, engine = _registry_and_engine()
    router = _router_from_engine(engine, reg)

    mem = MemoryPlatform(session_store=InMemoryMemoryStore())
    mem.remember_turn("wf:demo", "User prefers concise answers", role="user")

    exe = WorkflowExecutor(
        memory=mem,
        reflection=None,  # use default StepReflection via build_executor instead
    )
    exe = build_executor(memory=mem, session_id="wf:demo")

    plan = RuleBasedPlanner().plan("Summarize the report", PolicyContext(query=None))
    wf = Workflow(id="demo", goal="Summarize the report", plan=plan)

    out = exe.execute(wf, router)
    assert out.status == WorkflowStatus.DONE
    # memory context reached the prompt of at least the first step
    assert "User prefers concise answers" in router.last_prompt
    for s in out.plan:
        assert s.status == StepStatus.DONE
        assert s.route_used  # PolicyEngine chose a model


def test_workflow_survives_json_roundtrip_after_run():
    import json
    reg, engine = _registry_and_engine()
    router = _router_from_engine(engine, reg)
    exe = build_executor()
    wf = Workflow(id="rt", goal="explain X", plan=RuleBasedPlanner().plan("explain X", None))
    out = exe.execute(wf, router)
    restored = Workflow.from_json(out.to_json())
    assert restored.status == WorkflowStatus.DONE
    assert [s.output for s in restored.plan] == [s.output for s in out.plan]


def test_reflection_rejects_short_output_via_scorecard():
    from services.reflection import StepReflection
    refl = StepReflection(min_length=20)
    short = Step(id="s", task="t", output="too short", status=StepStatus.DONE)
    assert refl.evaluate_step(short) is False
    long = Step(id="s", task="t", output="this answer is definitely long enough", status=StepStatus.DONE)
    assert refl.evaluate_step(long) is True


def test_retry_manager_changes_route_via_tags():
    from services.retry_manager import RetryManager
    rm = RetryManager()
    q = ModelQuery(prompt="task")
    ctx = PolicyContext(query=q)
    q2, ctx2 = rm.prepare_retry(q, ctx, attempt=2)
    assert q2.reasoning is True          # attempt 2 escalates to reasoning
    assert ctx2.tags.get("retry_strategy") == "reasoning"
    q3, ctx3 = rm.prepare_retry(q2, ctx2, attempt=3)
    assert q3.local is True              # attempt 3 escalates to a local model
    assert ctx3.tags.get("retry_strategy") == "local"
