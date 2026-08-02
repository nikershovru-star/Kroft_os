"""Reference Reasoning Engine (ТЗ-RE-01) — deterministic, LLM-free (I-09).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

The Reasoning Engine is the PARAMETRIC engine of the Deliberate phase
(ADR-054: Reasoning -> Planning -> Decision). It reads the Intent + WorldState
(+ Attention context) and yields world-aware ReasoningSteps that become candidates
for the Planner. An LLM may later ADVISE, but the generation stays rule-based so
the LLM-free core invariant (I-09) holds.

Each ReasoningStep carries:
- a ConfidenceScore (ADR-054 I-12), raised when world facts support the step;
- the node's shared CausalMark (ТЗ-CAUSAL-01 / ТЗ-RE-01 flag 1) so reasoning is
  causally ordered on the same clock as kernel events + world facts;
- `based_on_facts`: which world keys the step actually read (world-awareness, and
  the negative-test hook: a step WITHOUT supporting facts is a different candidate).
"""

from __future__ import annotations

import uuid
from typing import List

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
    ReasoningStep,
    WorldState,
)
from contracts.i_cognitive_kernel import IAttention, IReasoningEngine
from contracts.i_cognitive_kernel import Intent


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class ReferenceReasoningEngine(IReasoningEngine):
    """Deterministic rule-based reasoning (LLM-free core).

    Strategy: for each salient world fact (selected by Attention within budget),
    emit a reasoning step that proposes a candidate plan direction grounded in that
    fact. If NO world fact is relevant, emit a single low-confidence "explore" step
    (so Planning still has a candidate — but a DIFFERENT one, which the negative test
    asserts). Confidence scales with how many intent words overlap the fact content.
    """

    def __init__(self, clock: NodeLamportClock, attention: IAttention) -> None:
        # ТЗ-RE-01 flag 1: reasoning advances the SAME shared node clock as the
        # kernel + world, so every reasoning step's CausalMark shares one order.
        self._clock = clock
        self._attention = attention

    def reason(self, intent: Intent, world: WorldState,
               attention_context: List[str], budget_tokens: int) -> List[ReasoningStep]:
        steps: List[ReasoningStep] = []
        intent_words = set(intent.text.lower().split())

        # world-aware: pick facts via Attention (respects budget + quota, I-05/I-06)
        salient = self._attention.select_context(intent, world, budget_tokens) if attention_context is None else attention_context

        for key in salient:
            content = world.facts.get(key, "")
            overlap = len(intent_words & set(content.lower().split()))
            # confidence rises with goal-relevance (overlap); floor 0.5 for a grounded step
            val = min(1.0, 0.5 + 0.1 * overlap)
            mark: CausalMark = self._clock.tick()
            steps.append(ReasoningStep(
                id=_uid("rsn"),
                goal_id="",  # filled by kernel once the Goal exists
                description=f"grounded-in:{key}",
                based_on_facts=(key,),
                confidence=ConfidenceScore(val, ProvenanceType.RULE_INFERENCE),
                causal=mark,
            ))

        # Negative-test hook: NO relevant world fact -> a single low-confidence
        # "explore" step. This is intentionally a DIFFERENT candidate than any
        # grounded step, proving reasoning depends on world state.
        if not steps:
            mark = self._clock.tick()
            steps.append(ReasoningStep(
                id=_uid("rsn"),
                goal_id="",
                description="explore:no-world-fact",
                based_on_facts=(),
                confidence=ConfidenceScore(0.3, ProvenanceType.RULE_INFERENCE),
                causal=mark,
            ))

        return steps
