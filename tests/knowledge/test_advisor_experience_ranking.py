"""Slice 8 — advisor plans also ride experience-ranking (consistency fix proof).

Proof (K5): the LLMAdvisorPlanner wraps ReferencePlanner; ReferencePlanner already ranks
candidates by experience, but the advisor's boosted plan was appended AFTER that and thus
bypassed experience-ranking. Now the advisor plan is run through self._apply_experience_ranking
before being inserted, so it is biased by past success_rate exactly like every other candidate.

- With exec:file success_rate 0.0 (failures) the advisor plan's confidence is LOWER than the
  raw advisor-boosted confidence (penalty applied).
- With exec:file success_rate 1.0 (success) the advisor plan's confidence is HIGHER than the
  raw advisor-boosted confidence (boost applied).
- advisor=None keeps the pure reference behaviour (existing tests stay green).

No new port/DTO/layer; kernel/llm_advisor only.
"""

from __future__ import annotations

from typing import Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    Goal,
    Intent,
    Provenance,
    ProvenanceType,
    WorldState,
)
from contracts.i_llm_advisor import AdviseContext, ILLMAdvisor
from composition.run_kroft import InMemoryProceduralMemory
from kernel.llm_advisor import LLMAdvisorPlanner
from kernel.planning import ReferencePlanner


class FakeAdvisor(ILLMAdvisor):
    """Advises the first available candidate description (deterministic, no real model)."""

    def advise(self, context: AdviseContext):
        descs = [d for d in context.candidate_descriptions if d]
        if not descs:
            return None
        return type("A", (), {
            "suggestion": descs[0],
            "confidence": ConfidenceScore(0.9, ProvenanceType.MODEL_INFERENCE),
            "provenance": Provenance(source="mock", actor="model"),
        })()


def _planner_with(sr: float):
    proc = InMemoryProceduralMemory()
    proc._procedures["exec:file"] = {
        "capability": "exec:file", "runs": 4,
        "successes": int(4 * sr), "success_rate": sr,
    }
    planner = LLMAdvisorPlanner(
        clock=None, advisor=FakeAdvisor(), procedural=proc)
    return planner


def _inputs():
    goal = Goal(id="g", intent_id="i", description="запиши hello в x.txt",
                confidence=ConfidenceScore(0.8),
                provenance=Provenance(source="test", actor="test"))
    intent = Intent(id="i", text="запиши hello в x.txt",
                    confidence=ConfidenceScore(0.8),
                    provenance=Provenance(source="test", actor="test"))
    world = WorldState(node_id="n1")
    return goal, intent, world


def test_advisor_plan_penalized_when_success_low():
    planner = _planner_with(0.0)
    goal, intent, world = _inputs()
    # raw advisor confidence = reference candidate confidence (already experience-biased
    # by super().plan) + 0.3 advisor boost, BEFORE the advisor plan is re-ranked.
    base = ReferencePlanner(clock=None, procedural=planner._procedural).plan(
        goal, [], world, 100, intent=intent)
    raw = min(1.0, base[0].confidence.value + 0.3)
    cands = planner.plan(goal, [], world, 100, intent=intent)
    advisor_plan = cands[0]  # advisor plan is moved to front
    assert advisor_plan.execution_steps and advisor_plan.execution_steps[0]["kind"] == "file"
    assert advisor_plan.confidence.value < raw, (advisor_plan.confidence.value, raw)


def test_advisor_plan_boosted_when_success_high():
    planner = _planner_with(1.0)
    goal, intent, world = _inputs()
    base = ReferencePlanner(clock=None, procedural=planner._procedural).plan(
        goal, [], world, 100, intent=intent)
    raw = min(1.0, base[0].confidence.value + 0.3)
    cands = planner.plan(goal, [], world, 100, intent=intent)
    advisor_plan = cands[0]
    assert advisor_plan.execution_steps and advisor_plan.execution_steps[0]["kind"] == "file"
    assert advisor_plan.confidence.value > raw, (advisor_plan.confidence.value, raw)


def test_advisor_none_keeps_pure_behaviour():
    # advisor=None -> LLMAdvisorPlanner must equal ReferencePlanner (no advisor plan added)
    proc = InMemoryProceduralMemory()
    proc._procedures["exec:file"] = {
        "capability": "exec:file", "runs": 4, "successes": 4, "success_rate": 1.0}
    planner = LLMAdvisorPlanner(clock=None, advisor=None, procedural=proc)
    ref = ReferencePlanner(clock=None, procedural=proc)
    goal, intent, world = _inputs()
    a = planner.plan(goal, [], world, 100, intent=intent)
    b = ref.plan(goal, [], world, 100, intent=intent)
    assert [p.confidence.value for p in a] == [p.confidence.value for p in b]
