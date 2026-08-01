"""(tests) Wave 10 (ADR-013) Phase G — LIVE golden test (gated).

A real two-step workflow executed through the actual Router + a real adapter
(OmniRoute / Ollama), proving the orchestration works end-to-end against a
live model. Gated behind WORKFLOW_LIVE=1 so the default suite never needs a
model or network (LAW: suite must be green offline).

Run manually:
    WORKFLOW_LIVE=1 python -m pytest tests/test_workflow_live.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_workflow import StepStatus, Workflow, WorkflowStatus
from contracts.i_llm import ModelQuery
from adapters.rule_based_planner import RuleBasedPlanner
from services.workflow_runner import build_executor
from contracts.model_registry import ModelRegistry
from policies.budget_policy import BudgetPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from adapters.router import Router


pytestmark = pytest.mark.skipif(
    os.environ.get("WORKFLOW_LIVE") != "1",
    reason="live workflow test gated behind WORKFLOW_LIVE=1",
)


def _build_router(base_url: str = "http://localhost:20128"):
    """Wire a real router using a real HTTP adapter (OmniRoute free gateway)."""
    from adapters.omni_route_adapter import OmniRouteAdapter

    reg = ModelRegistry()
    for mid, prov, local, free in [
        ("phi4", "ollama", True, True),
        ("gpt-mini", "openai", False, False),
    ]:
        reg.register_model(ModelInfo(
            id=mid, provider=prov, local=local, free=free,
            reasoning=(mid == "gpt-mini"), context_window=32000,
        ))
    adapters = {
        "ollama": OmniRouteAdapter(reg.catalog()[0], base_url=base_url),
        "openai": OmniRouteAdapter(reg.catalog()[1], base_url=base_url),
    }
    engine = PolicyEngine(reg)
    engine.register(BudgetPolicy())
    engine.register(ProviderSelectionPolicy())
    return Router(engine, adapters)


def test_two_step_workflow_runs_live():
    router = _build_router()
    exe = build_executor(session_id="wf:live")
    plan = RuleBasedPlanner().plan("Summarize the concept of ownership in Rust", None)
    wf = Workflow(id="live-1", goal="Summarize the concept of ownership in Rust", plan=plan)
    out = exe.execute(wf, router)
    assert out.status == WorkflowStatus.DONE
    assert all(s.status == StepStatus.DONE for s in out.plan)
    assert out.plan[1].output.strip()  # a real summary came back


def test_workflow_replayable_after_live_run():
    import json
    router = _build_router()
    exe = build_executor(session_id="wf:live2")
    wf = Workflow(
        id="live-2",
        goal="Explain why Rust has no garbage collector",
        plan=RuleBasedPlanner().plan("Explain why Rust has no garbage collector", None),
    )
    out = exe.execute(wf, router)
    replay = Workflow.from_json(out.to_json())
    assert replay.status == WorkflowStatus.DONE
    assert json.loads(replay.to_json()) == json.loads(out.to_json())
