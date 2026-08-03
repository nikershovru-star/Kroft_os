"""Reference Reflection Engine (ТЗ-RF-01) — deterministic, LLM-free (I-09).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

Reflection is the ANALYTIC part of Self-Evolving (round 2 cognitive reflection). It
looks at accumulated experience and PROPOSES (does not write) evolution of the SOFT
layer. Committing proposals under the O1 Self-Evolving guard is the job of Memory
Evolution / the kernel Learn phase.

Addresses ФЛАГ 1 (ТЗ-ME-01): outcome-based. Successful high-utility experience is
proposed for consolidation; repeated unsuccessful experience is proposed for
deprecation. It does NOT merely repeat intent text.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    CausalMark,
    ExecutionOutcome,
    NodeLamportClock,
    Policy,
    ProvenanceType,
    ReflectionReport,
    SemanticFact,
)
from contracts.i_reflection import IReflectionEngine


class ReferenceReflectionEngine(IReflectionEngine):
    """Deterministic outcome-based reflection (ТЗ-RF-01, I-09).

    Args:
        clock: shared node Lamport clock (ТЗ-RE-01 flag 1) — CausalMark source.
        utility_threshold: minimum utility for a successful experience to be a
            consolidation candidate.
        min_repetitions: minimum number of repeated outcomes before a proposal is made.
    """

    def __init__(self,
                 clock: NodeLamportClock,
                 utility_threshold: float = 0.6,
                 min_repetitions: int = 2) -> None:
        self._clock = clock
        self._utility_threshold = utility_threshold
        self._min_repetitions = min_repetitions

    def reflect(self,
                memory,  # ILayeredMemory
                world,  # IWorldState
                recent_events: Optional[List[object]] = None,
                outcomes: Optional[List[ExecutionOutcome]] = None) -> ReflectionReport:
        outcomes = outcomes or []
        episodes = memory.get_episodes() if memory is not None else []
        # No experience to reflect on -> empty report (negative-test anchor).
        if not episodes and not outcomes:
            return ReflectionReport()

        mark = self._clock.tick()  # causally ordered reflection mark
        consolidation: List[SemanticFact] = []
        deprecation: List[str] = []
        policy_suggestions: List[Policy] = []
        insights: List[str] = []

        # OUTCOME-BASED analysis (ФЛАГ 1). Group outcomes by episode summary/content
        # to find repeated SUCCESS vs FAILURE patterns.
        success_keys: Counter = Counter()
        fail_keys: Counter = Counter()
        success_utils: "Counter" = Counter()  # summed utility per key
        for o in outcomes:
            # derive a reflection key from the episode's content if available
            key = self._key_for(memory, o.episode_id)
            if o.success and o.utility >= self._utility_threshold:
                success_keys[key] += 1
                success_utils[key] += o.utility
            elif not o.success:
                fail_keys[key] += 1

        for key, n in success_keys.items():
            if n >= self._min_repetitions:
                avg_util = success_utils[key] / n
                consolidation.append(SemanticFact(
                    id=f"refcons:{key}",
                    content=key,
                    confidence=ConfidenceScore(round(min(1.0, avg_util), 3),
                                               ProvenanceType.REFLECTION),
                    causal=mark,
                    source_episodes=tuple(),
                ))
                insights.append(f"successful pattern consolidated: {key} (n={n})")

        for key, n in fail_keys.items():
            if n >= self._min_repetitions:
                deprecation.append(key)
                insights.append(f"unsuccessful pattern deprecated: {key} (n={n})")

        # Semantic layer already present -> propose strengthening (re-surface as insight)
        semantic = memory.get_semantic() if memory is not None else []
        if semantic:
            insights.append(f"semantic layer holds {len(semantic)} fact(s)")

        confidence = ConfidenceScore(
            round(min(1.0, 0.5 + 0.1 * (len(consolidation) + len(deprecation))), 3),
            ProvenanceType.REFLECTION)

        return ReflectionReport(
            consolidation_candidates=tuple(consolidation),
            deprecation_candidates=tuple(deprecation),
            policy_suggestions=tuple(policy_suggestions),  # SOFT-only; reference emits none
            insights=tuple(insights),
            confidence=confidence,
            causal=mark,
        )

    @staticmethod
    def _key_for(memory, episode_id: str) -> str:
        """Derive a stable reflection key from the episode content (not intent text)."""
        for ep in memory.get_episodes():
            if ep.id == episode_id:
                return ep.summary
        return episode_id
