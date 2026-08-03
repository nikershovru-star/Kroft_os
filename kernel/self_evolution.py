"""Self-Evolution behavioral-closure — LLM-FREE reference implementation (ТЗ-SE-01, ADR-064).

K1-compliant: stdlib + contracts only. Deterministic (I-09).

Closes ФЛАГ 3 (ТЗ-EX-01): deliberation reads the EVOLVED SOFT layer so self-evolution
changes BEHAVIOR, not just memory.

Three read-side components (no mutation of HARD/FSM/contracts — O1):
- MemorySoftPolicySource(ISoftPolicySource): reads ILayeredMemory (SOFT soft policies
  + semantic facts) and exposes prefer/avoid/recall to deliberation.
- PolicyAwareValueSystem(SimpleValueSystem): score() adds bonuses for prefer-patterns
  and penalties for avoid-patterns found in candidate plan steps. Soft-only influence.
- KnowledgeAwareReasoning(ReferenceReasoningEngine): reason() surfaces consolidated
  semantic facts (e.g. 'decided:<action>') as grounded candidate directions, so the
  planner/decision see the learned layer as explicit candidates.
"""

from __future__ import annotations

from typing import List, Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    ProvenanceType,
    ReasoningStep,
    WorldState,
    Intent,
)
from contracts.i_cognitive_kernel import IValueSystem
from contracts.i_self_evolution import ISoftPolicySource, SoftPolicyPreference

from kernel.cognitive_kernel import SimpleValueSystem
from kernel.reasoning import ReferenceReasoningEngine


class MemorySoftPolicySource(ISoftPolicySource):
    """Reads the evolved SOFT layer from ILayeredMemory (K6: via the port, not import)."""

    def __init__(self, memory) -> None:
        # memory: ILayeredMemory — never mutated here.
        self._memory = memory

    def get_prefer_patterns(self) -> List[str]:
        out: List[str] = []
        for p in self._memory.get_normative():
            if getattr(p, "layer", None) == "soft" and "avoid" not in p.body:
                out.append(p.body)
        # also surface successful consolidated facts as recall (see get_recall_facts)
        return out

    def get_avoid_patterns(self) -> List[str]:
        out: List[str] = []
        for p in self._memory.get_normative():
            if getattr(p, "layer", None) == "soft" and "avoid" in p.body:
                # body形如 'avoid:<pattern>' -> strip prefix
                out.append(p.body.split(":", 1)[1] if ":" in p.body else p.body)
        return out

    def get_recall_facts(self) -> List[str]:
        # consolidated semantic facts, e.g. 'decided:<action>'
        return [f.content for f in self._memory.get_semantic()]


class PolicyAwareValueSystem(SimpleValueSystem):
    """Two-layer value system that also consults the evolved SOFT policy layer (O1:
    SOFT-only influence; HARD layer untouched)."""

    def __init__(self, source: Optional[ISoftPolicySource] = None,
                 hard_checkers=None, weights=None) -> None:
        super().__init__(hard_checkers=hard_checkers, weights=weights)
        self._source = source

    def attach_source(self, source: ISoftPolicySource) -> None:
        self._source = source

    def score(self, candidate: object) -> float:
        base = super().score(candidate)
        if self._source is None:
            return base
        steps = " ".join(getattr(candidate, "steps", ()) or ())
        total = 0.0
        for pref in self._source.get_preferences():
            if pref.pattern and pref.pattern in steps:
                total += pref.weight
        return base + total  # prefer raises, avoid lowers; never touches HARD


class KnowledgeAwareReasoning(ReferenceReasoningEngine):
    """Reasoning that surfaces the evolved SOFT semantic layer as candidate directions
    (O1: read-only; does not mutate FSM/memory/contracts)."""

    def __init__(self, clock, attention, source: Optional[ISoftPolicySource] = None) -> None:
        super().__init__(clock, attention)
        self._source = source

    def attach_source(self, source: ISoftPolicySource) -> None:
        self._source = source

    def reason(self, intent: Intent, world: WorldState,
               attention_context: Optional[List[str]], budget_tokens: int) -> List[ReasoningStep]:
        steps = super().reason(intent, world, attention_context, budget_tokens)
        if self._source is None:
            return steps
        # Surface consolidated learned facts as grounded candidate directions.
        for fact in self._source.get_recall_facts():
            mark = self._clock.tick()
            steps.append(ReasoningStep(
                id=f"rsn-recall-{abs(hash(fact)) % 10_000}",
                goal_id="",
                description=f"grounded-in:{fact}",
                based_on_facts=(fact,),
                confidence=ConfidenceScore(0.85, ProvenanceType.REFLECTION),
                causal=mark,
            ))
        return steps
