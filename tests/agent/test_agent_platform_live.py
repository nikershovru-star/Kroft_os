"""(tests) Wave 11 (ADR-014) Phase G — LIVE golden test (gated).

Assembles the REAL subsystems (RuleBasedPlanner, WorkflowExecutor, MemoryPlatform,
PolicyEngine + Router, OmniRouteAdapter) and runs one agent goal end-to-end
against a live model. Gated behind AGENT_LIVE=1 so the default suite needs no
model or network (LAW: suite must be green offline).

Run manually:
    AGENT_LIVE=1 python -m pytest tests/test_agent_platform_live.py -v
"""
import os
import sys

import pytest

from contracts.i_agent_platform import AgentStatus
from contracts.i_workflow import WorkflowStatus
from adapters.rule_based_planner import RuleBasedPlanner
from services.workflow_runner import build_executor
from services.memory_platform import MemoryPlatform
from adapters.in_memory_memory_store import InMemoryMemoryStore
from contracts.model_registry import ModelRegistry
from policies.budget_policy import BudgetPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from adapters.router import Router
from services.agent_platform import AgentPlatform


pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_LIVE") != "1",
    reason="live agent test gated behind AGENT_LIVE=1",
)


def _build_agent(base_url: str = "http://localhost:20128"):
    from adapters.omni_route_adapter import OmniRouteAdapter
    from contracts.i_llm import ModelInfo

    reg = ModelRegistry()
    for mid, prov, local, free, reason in [
        ("phi4", "ollama", True, True, False),
        ("gpt-mini", "openai", False, False, True),
    ]:
        reg.register_model(ModelInfo(id=mid, provider=prov, local=local, free=free,
                                      reasoning=reason, context_window=32000))
    adapters = {
        "ollama": OmniRouteAdapter(reg.catalog()[0], base_url=base_url),
        "openai": OmniRouteAdapter(reg.catalog()[1], base_url=base_url),
    }
    engine = PolicyEngine(reg)
    engine.register(BudgetPolicy())
    engine.register(ProviderSelectionPolicy())
    router = Router(engine, adapters)
    mem = MemoryPlatform(session_store=InMemoryMemoryStore())
    executor = build_executor(memory=mem, session_id="agent:live")
    return AgentPlatform(
        planner=RuleBasedPlanner(),
        executor=executor,
        router=router,
        memory=mem,
        session_id="agent:live",
    )


def test_agent_run_live():
    agent = _build_agent()
    res = agent.run("Explain why Rust has no garbage collector")
    assert res.status == AgentStatus.DONE
    assert res.workflow.status == WorkflowStatus.DONE
    assert any(s.output.strip() for s in res.workflow.plan)
    assert res.memory_refs  # memory was written
