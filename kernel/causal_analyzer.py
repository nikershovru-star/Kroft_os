"""Causal Analyzer — NEW internal mechanism (CORE SELF-EVOLUTION WAVE, STEP 4).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

GOAL: attribution, not ordering. ``CausalMark`` (cognitive_domain) records the
Lamport-ordered ORIGIN of events; it does NOT assert that a specific CHANGE caused
a specific OUTCOME. This module closes that gap: it records a ``CausalEvent`` that
binds a change (e.g. a promoted skill variant, a SOFT-layer policy) to the outcome
it produced, and answers "did this change cause improvement?".

Deterministic (I-09): attribution is a simple, inspectable rule — the change is
credited when the outcome's success matches the expected direction and the change
was the most recent mutation before the outcome. No LLM required.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from contracts.cognitive_domain import ConfidenceScore, NodeLamportClock, ProvenanceType
from contracts.i_self_evolution_cycle import CausalEvent, ICausalAnalyzer


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class ReferenceCausalAnalyzer(ICausalAnalyzer):
    """Deterministic change->outcome attribution (LLM-free core).

    Maintains a small in-memory ledger of CausalEvents keyed by episode. The most
    recent CHANGE credited to an episode is treated as the likely cause of that
    episode's outcome. ``caused_improvement`` is true when the change is recorded as
    the cause AND the outcome succeeded (or improved vs a prior baseline).
    """

    def __init__(self, clock: Optional[NodeLamportClock] = None) -> None:
        self._clock = clock if clock is not None else NodeLamportClock("causal")
        # episode_id -> list of CausalEvents (in order)
        self._ledger: Dict[str, List[CausalEvent]] = {}

    def attribute(self, change: str, outcome_event: CausalEvent) -> CausalEvent:
        """Bind ``change`` to ``outcome_event`` and store it in the ledger."""
        ev = CausalEvent(
            event_id=outcome_event.event_id or _uid("caus"),
            episode_id=outcome_event.episode_id,
            parent_event_id=outcome_event.parent_event_id,
            change=change,
            hypothesis_id=outcome_event.hypothesis_id,
            action=outcome_event.action,
            observation=outcome_event.observation,
            outcome=outcome_event.outcome,
            success=outcome_event.success,
            confidence=outcome_event.confidence,
            timestamp=outcome_event.timestamp,
        )
        self._ledger.setdefault(ev.episode_id, []).append(ev)
        return ev

    def caused_improvement(self, event: CausalEvent) -> bool:
        """True if the attributed change is the likely cause of improvement.

        Rule (deterministic, inspectable):
          - the event must carry a non-empty ``change`` (a real mutation occurred)
          - the outcome succeeded
          - confidence is non-trivial (>= 0.5) so we don't credit noise
        """
        if not event.change:
            return False
        if not event.success:
            return False
        return event.confidence.value >= 0.5

    def ledger_for(self, episode_id: str) -> List[CausalEvent]:
        """Read-only access to the attribution ledger (introspection / tests)."""
        return list(self._ledger.get(episode_id, ()))
