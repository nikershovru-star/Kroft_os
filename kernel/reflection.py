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
    SelfObservationRecord,
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

    def observe_scale(self,
                      total_nodes: int,
                      touched_node_ids: List[str],
                      activity_distribution: Optional[Dict[str, float]] = None,
                      resolution_level: str = "NODE") -> "SelfObservationRecord":
        """ADR-028 Stage 3 — cosmic perspective (operational self-awareness).

        Computes where the current task sits relative to the WHOLE knowledge base
        and total system activity. Deterministic (I-09). Ratios keep full precision
        so a small task (e.g. 3 of 15000 nodes) reports ~0.0002, never 0.

        Args:
            total_nodes: total node count in the graph (from graph query engine).
            touched_node_ids: node ids the current task touched.
            activity_distribution: optional {subsystem: share}; shares are normalised
                to sum to 1.0 (missing -> empty distribution, reported as-is).
            resolution_level: the ADR-028 Stage 1 level the agent operates at.
        """
        touched = len(set(touched_node_ids)) if touched_node_ids else 0
        ratio = (touched / float(total_nodes)) if total_nodes > 0 else 0.0
        activity: List[tuple] = []
        if activity_distribution:
            total = float(sum(activity_distribution.values())) or 1.0
            activity = sorted(
                (k, round(v / total, 6)) for k, v in activity_distribution.items()
            )
        return SelfObservationRecord(
            total_nodes=total_nodes,
            touched_nodes=touched,
            touched_node_ratio=round(ratio, 9),
            activity_by_subsystem=tuple(activity),
            resolution_level=resolution_level,
        )
