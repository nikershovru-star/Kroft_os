"""LLM-as-advisor reference implementation (ТЗ-LLM-01, ADR-065).

K1-compliant: stdlib + contracts only. LLM-FREE core is PRESERVED — the advisor
is OPTIONAL. When an ILLMAdvisor is wired, reasoning/planning read its advice to
re-rank candidate plans; when it raises (unavailable/timeout) the implementation
falls back to the PURE reference path and yields the EXACT same result as if no
advisor were present. That equality IS the proof that the kernel is LLM-free by
construction (I-10, kernel purity), not just by declaration.

Design invariants (O1 / K6 / K8):
  - The LLM NEVER makes the final selection. It only adds a boosted ReasoningStep /
    a re-ranked Plan. The deterministic Decision Engine still picks (I-03).
  - The advisor cannot mutate HARD layer, FSM, or contracts. It is read-only here.
  - On exception, fallback == no-advisor result (deterministic, graceful, no crash).
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Plan,
    Provenance,
    ProvenanceType,
    ReasoningStep,
    WorldState,
)
from contracts.i_llm_advisor import (
    AdviseContext,
    ILLMAdvisor,
    LLMError,
    LLMTimeout,
)
from contracts.i_observability import ILiveMetricsCollector, METRIC_LLM_FALLBACK_RATE
from kernel.reasoning import ReferenceReasoningEngine
from kernel.self_evolution import KnowledgeAwareReasoning
from kernel.planning import ReferencePlanner


class MockLLMClient(ILLMAdvisor):
    """Deterministic, rule-based advisor for tests / offline use (no real model).

    Strategy: if the intent text names one of the candidate descriptions, advise
    that candidate (boosting it). Otherwise return None (no suggestion). If
    ``fail=True`` it raises ``LLMError`` to exercise the graceful-fallback path.
    """
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def advise(self, context: AdviseContext) -> Optional[object]:
        if self._fail:
            raise LLMError("mock advisor unavailable")
        lower = context.intent_text.lower()
        for cand in context.candidate_descriptions:
            if cand and cand.lower() in lower:
                return type("A", (), {  # lightweight advice-like object
                    "suggestion": cand,
                    "confidence": ConfidenceScore(0.9, ProvenanceType.MODEL_INFERENCE),
                    "provenance": Provenance(source="mock_llm", actor="model"),
                })()
        return None


class LLMAdvisorReasoning(KnowledgeAwareReasoning):
    """Reasoning that MAY read an LLM advisor, but never depends on it.

    Falls back to the pure reference reasoning when the advisor is absent or raises.
    The advisor only ADDS a boosted ReasoningStep (it cannot remove or mutate the
    reference steps, nor the FSM/HARD layer).
    """
    def __init__(self, clock, attention, source=None, advisor: Optional[ILLMAdvisor] = None) -> None:
        super().__init__(clock, attention, source)
        self._advisor = advisor
        self._collector: Optional[ILiveMetricsCollector] = None  # ТЗ-OBS-01 Флаг 2 / ТЗ-LLM-02

    def attach_advisor(self, advisor: Optional[ILLMAdvisor]) -> None:
        self._advisor = advisor

    def attach_metrics(self, collector: Optional[ILiveMetricsCollector]) -> None:
        """ТЗ-OBS-01 Флаг 2 / ТЗ-LLM-02: wire a live metrics collector so advisor
        fallback (LLMError/LLMTimeout) increments ``llm.fallback_rate``. No-op if None."""
        self._collector = collector

    def reason(self, intent: Intent, world: WorldState,
               attention_context, budget_tokens: int):
        steps = super().reason(intent, world, attention_context, budget_tokens)
        if self._advisor is None:
            return steps
        try:
            ctx = AdviseContext(
                intent_text=intent.text,
                world_facts=tuple(world.snapshot().keys()) if hasattr(world, "snapshot") else (),
                candidate_descriptions=(),
            )
            advice = self._advisor.advise(ctx)
        except (LLMError, LLMTimeout):
            # graceful fallback: the pure reference steps stand unchanged
            if self._collector is not None:
                self._collector.record_failure(METRIC_LLM_FALLBACK_RATE)
            return steps
        if advice is None or not getattr(advice, "suggestion", ""):
            return steps
        boosted = ReasoningStep(
            id=f"llm-{intent.id}",
            goal_id=intent.id if hasattr(intent, "id") else "goal",
            description=f"llm-advice:{advice.suggestion}",
            based_on_facts=("llm-advisor",),
            confidence=getattr(
                advice, "confidence",
                ConfidenceScore(0.9, ProvenanceType.MODEL_INFERENCE),
            ),
        )
        return steps + [boosted]


class LLMAdvisorPlanner(ReferencePlanner):
    """Planner that MAY re-rank candidates using an LLM advisor, but never selects.

    On exception (or no advisor) it delegates to the PURE reference planner, yielding
    the EXACT same candidates/order as if no advisor existed — proving the kernel is
    LLM-free by construction. The advisor only adds ONE re-ranked (boosted) Plan; the
    deterministic Decision Engine makes the final pick (I-03).
    """
    def __init__(self, clock, world_model=None, values=None, advisor: Optional[ILLMAdvisor] = None) -> None:
        super().__init__(clock, world_model=world_model, values=values)
        self._advisor = advisor
        self._collector: Optional[ILiveMetricsCollector] = None  # ТЗ-OBS-01 Флаг 2 / ТЗ-LLM-02

    def attach_advisor(self, advisor: Optional[ILLMAdvisor]) -> None:
        self._advisor = advisor

    def attach_metrics(self, collector: Optional[ILiveMetricsCollector]) -> None:
        """ТЗ-OBS-01 Флаг 2 / ТЗ-LLM-02: wire collector so advisor fallback
        increments ``llm.fallback_rate``. No-op if None."""
        self._collector = collector

    def plan(self, goal, reasoning_steps, world, budget_tokens, intent=None):
        base = super().plan(goal, reasoning_steps, world, budget_tokens, intent=intent)
        if self._advisor is None or not base:
            return base
        try:
            ctx = AdviseContext(
                intent_text=intent.text if intent is not None else "",
                world_facts=tuple(world.snapshot().keys()) if hasattr(world, "snapshot") else (),
                candidate_descriptions=tuple(p.steps[0] if p.steps else "" for p in base),
            )
            advice = self._advisor.advise(ctx)
        except (LLMError, LLMTimeout):
            # graceful fallback: pure reference plan list (unchanged)
            if self._collector is not None:
                self._collector.record_failure(METRIC_LLM_FALLBACK_RATE)
            return base
        if advice is None or not getattr(advice, "suggestion", ""):
            return base
        # re-rank: promote the advised candidate by boosting its confidence
        target = getattr(advice, "suggestion", "")
        boosted_list = []
        for p in base:
            if p.steps and p.steps[0] == target:
                boosted = dataclasses.replace(
                    p,
                    confidence=ConfidenceScore(
                        min(1.0, (p.confidence.value if isinstance(p.confidence, ConfidenceScore) else 0.5) + 0.3),
                        ProvenanceType.MODEL_INFERENCE,
                    ),
                )
                boosted_list.insert(0, boosted)  # move to front (best-first)
            else:
                boosted_list.append(p)
        return boosted_list
