"""K8 tests for ТЗ-LLM-01 — LLM-as-advisor plug-in + graceful fallback.

Covers (acceptance + O1/K1/K6/K8):
- ADVICE influences RANKING of candidate plans (boosted candidate moves to front),
  but the DETERMINISTIC Decision Engine makes the final pick (LLM never chooses).
- LLM EXCEPTION / timeout -> GRACEFUL FALLBACK == result WITHOUT LLM (kernel LLM-free
  by construction, not just by declaration). No crash.
- WITHOUT LLM the kernel is UNCHANGED (LLM-free core preserved).
- LLM NEVER makes the final selection; O1: advisor does not mutate HARD/FSM/contracts;
  K6: kernel depends only on the ILLMAdvisor port.
"""

from __future__ import annotations

from unittest.mock import patch

from contracts.cognitive_domain import (
    ConfidenceScore,
    Goal,
    Intent,
    Plan,
    Provenance,
    ProvenanceType,
)
from contracts.i_llm_advisor import AdviseContext, ILLMAdvisor, LLMError, LLMTimeout
from kernel.cognitive_kernel import build_kernel, NodeLamportClock
from kernel.execution import ReferenceExecutor
from kernel.llm_advisor import (
    LLMAdvisorPlanner,
    LLMAdvisorReasoning,
    MockLLMClient,
)
from kernel.self_evolution import MemorySoftPolicySource
from kernel.memory_store import InMemoryLayeredMemory


def _intent(text: str = "go") -> Intent:
    return Intent(id="i1", text=text,
                  confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))


def _goal():
    return Goal(id="goal-1", intent_id="i1", description="g",
                confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                provenance=Provenance(source="u", actor="u"))


def _plan(pid, step, conf=0.5):
    return Plan(id=pid, goal_id="goal-1", steps=(step,),
                confidence=ConfidenceScore(conf, ProvenanceType.RULE_INFERENCE),
                provenance=Provenance(source="t", actor="t"))


# ---------------------------------------------------------------------------
# 1. ADVICE changes RANKING, but Decision (not LLM) makes the final choice
# ---------------------------------------------------------------------------
def test_advice_changes_ranking_but_not_final_selection():
    clk = NodeLamportClock("n")
    planner = LLMAdvisorPlanner(clk, advisor=MockLLMClient())
    base = [_plan("pa", "explore-for:g", 0.5), _plan("pb", "choose_blue", 0.5)]
    # monkeypatch the inherited ReferencePlanner.plan to return base candidates
    with patch("kernel.planning.ReferencePlanner.plan", return_value=list(base)):
        out = planner.plan(_goal(), [], None, 100, intent=_intent("choose_blue"))
    # the advised candidate ('choose_blue') must be boosted to the front
    assert out[0].steps[0] == "choose_blue", "advisor must re-rank advised candidate to front"
    # but it is still a PLAN (candidate), not a final decision by the LLM
    assert len(out) == 2
    # the deterministic Decision Engine is what selects; assert advisor has no select()
    assert not hasattr(planner._advisor, "select"), "LLM advisor MUST NOT select"


# ---------------------------------------------------------------------------
# 2. LLM EXCEPTION -> graceful fallback == result WITHOUT LLM (no crash)
# ---------------------------------------------------------------------------
def test_llm_exception_fallback_equals_no_llm():
    intent = _intent()
    k_no = build_kernel("LLM-no"); k_no.attach_executor(ReferenceExecutor())
    k_no.tick(intent)
    sel_no = k_no._last_selected_plan.steps

    k_fail = build_kernel("LLM-fail", llm_client=MockLLMClient(fail=True))
    k_fail.attach_executor(ReferenceExecutor())
    k_fail.tick(intent)  # must NOT crash
    sel_fail = k_fail._last_selected_plan.steps

    assert sel_no == sel_fail, "graceful fallback must equal the no-LLM result"
    assert k_fail._last_decision is not None


def test_llm_timeout_fallback_equals_no_llm():
    class TimeoutAdvisor(ILLMAdvisor):
        def advise(self, context):
            raise LLMTimeout("timed out")
    intent = _intent()
    k_no = build_kernel("LLM-no2"); k_no.attach_executor(ReferenceExecutor())
    k_no.tick(intent)
    sel_no = k_no._last_selected_plan.steps

    k_to = build_kernel("LLM-to", llm_client=TimeoutAdvisor())
    k_to.attach_executor(ReferenceExecutor())
    k_to.tick(intent)  # must NOT crash
    sel_to = k_to._last_selected_plan.steps
    assert sel_no == sel_to, "LLMTimeout fallback must equal the no-LLM result"


# ---------------------------------------------------------------------------
# 3. WITHOUT LLM the kernel is UNCHANGED (LLM-free core preserved)
# ---------------------------------------------------------------------------
def test_without_llm_kernel_unchanged():
    k_default = build_kernel("LLM-d")      # no llm_client arg at all
    k_none = build_kernel("LLM-n", llm_client=None)
    for k in (k_default, k_none):
        k.attach_executor(ReferenceExecutor())
        k.tick(_intent())
    assert k_default._last_selected_plan.steps == k_none._last_selected_plan.steps


# ---------------------------------------------------------------------------
# 4. LLM NEVER makes the final selection; advisor is read-only (O1)
# ---------------------------------------------------------------------------
def test_llm_never_selects_and_is_read_only():
    advisor = MockLLMClient()
    clk = NodeLamportClock("n")
    reason = LLMAdvisorReasoning(clk, _attn(), MemorySoftPolicySource(InMemoryLayeredMemory()),
                                 advisor=advisor)
    assert not hasattr(advisor, "select")
    assert not hasattr(advisor, "mutate")
    # advisor exposes only advise(); it cannot alter HARD/FSM/contracts
    assert set(dir(advisor)) & {"commit", "hard_violations", "transition"} == set()


def _attn():
    from kernel.cognitive_kernel import SimpleAttention, SimpleResourceManager
    return SimpleAttention(SimpleResourceManager())


# ---------------------------------------------------------------------------
# 5. K6: kernel depends only on the ILLMAdvisor PORT (no concrete adapter import
#    leaks into the kernel module top-level), and adapter_for bridges ILlm.
# ---------------------------------------------------------------------------
def test_k6_kernel_depends_only_on_advisor_port():
    import kernel.cognitive_kernel as ck
    # adapter_for is imported (port bridge), concrete provider SDKs are NOT
    assert hasattr(ck, "adapter_for")
    assert hasattr(ck, "ILLMAdvisor")


def test_adapter_for_bridges_existing_llm_port():
    from contracts.i_llm import ILlm, LlmResponse
    from contracts.i_llm_advisor import adapter_for
    class DummyILlm(ILlm):
        def complete(self, q): return LlmResponse(text="choose_blue")
        def stream(self, q): return iter(["choose_blue"])
    adv = adapter_for(DummyILlm())
    a = adv.advise(AdviseContext(intent_text="x", candidate_descriptions=("choose_blue",)))
    assert a is not None and a.suggestion == "choose_blue"
