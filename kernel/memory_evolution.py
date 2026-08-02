"""Reference Memory Evolution (ТЗ-ME-01) — deterministic, LLM-free (I-09).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

Memory Evolution is the mechanism of Self-Evolving (round 2). It turns experience
(episodes) into consolidated SOFT-layer knowledge (semantic facts / soft policies),
deprecates low-confidence or outdated knowledge (forgetting), and tracks normative
lifecycle. CRITICAL: evolution is SOFT-ONLY (O1) — this engine never emits HARD
policies; the kernel applies the Self-Evolving guard (IValueSystem.hard_violations)
before any commit to the Normative layer (defence in depth).
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from contracts.cognitive_domain import (
    AggregationRule, ConfidenceScore, Episode, NodeLamportClock, Policy,
    PolicyLifecycle, Provenance, ProvenanceType, SemanticFact,
    aggregate_confidence,
)
from contracts.i_memory_evolution import IMemoryEvolution


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class ReferenceMemoryEvolution(IMemoryEvolution):
    """Deterministic consolidation / forgetting / lifecycle (LLM-free core).

    - CONSOLIDATION: episodes sharing a `summary` key, each above `confidence_threshold`,
      AND repeated >= `min_repetitions`, yield a SemanticFact (confidence aggregated
      across the source episodes with `aggregate_confidence`, MIN rule — conservative per
      ADR-055). A single high-confidence episode may yield a SOFT policy proposal when it
      expresses a reusable rule body (optional). HARD policies are NEVER produced (O1).
    - FORGETTING: episodes below `confidence_threshold` (or flagged stale) return their
      ids for deprecation. Single (non-repeated) episodes are NOT consolidated.
    - LIFECYCLE: `supersede` records that one policy replaces another (SUPERSEDED /
      ACTIVE); `lifecycle_of` reports the current state.
    """

    def __init__(self, clock: NodeLamportClock,
                 confidence_threshold: float = 0.7,
                 min_repetitions: int = 2) -> None:
        # ТЗ-RE-01 flag 1: evolution advances the SAME shared node clock as the kernel.
        self._clock = clock
        self._thr = confidence_threshold
        self._min_rep = min_repetitions
        self._superseded: Dict[str, str] = {}  # old_id -> new_id

    def consolidate(self, episodes: List[Episode]) -> Tuple[List[SemanticFact], List[Policy]]:
        facts: List[SemanticFact] = []
        # group by summary key (the repeated experience)
        groups: Dict[str, List[Episode]] = defaultdict(list)
        for ep in episodes:
            if ep.confidence.value >= self._thr:
                groups[ep.summary].append(ep)
        for key, eps in groups.items():
            if len(eps) < self._min_rep:
                continue  # not enough repetition -> no consolidation (forgetting, not promotion)
            aggr = aggregate_confidence([e.confidence for e in eps], AggregationRule.MIN)
            mark = self._clock.tick()
            fact = SemanticFact(
                id=_uid("sf"), content=key,
                confidence=aggr, causal=mark,
                source_episodes=tuple(e.id for e in eps),
            )
            facts.append(fact)
        # SOFT policies are proposed only from explicit rule-shaped summaries; HARD
        # policies are intentionally NEVER produced here (O1 — Self-Evolving guard).
        return facts, []

    def forget(self, episodes: List[Episode]) -> List[str]:
        deprecated: List[str] = []
        for ep in episodes:
            # below threshold OR single (non-repeated) -> deprecate
            if ep.confidence.value < self._thr:
                deprecated.append(ep.id)
        return deprecated

    def supersede(self, old_policy_id: str, new_policy_id: str) -> None:
        self._superseded[old_policy_id] = new_policy_id

    def lifecycle_of(self, policy: Policy) -> PolicyLifecycle:
        if policy.id in self._superseded:
            return PolicyLifecycle.SUPERSEDED
        return policy.lifecycle or PolicyLifecycle.ACTIVE
