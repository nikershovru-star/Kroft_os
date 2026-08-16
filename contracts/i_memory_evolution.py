"""Memory Evolution port (ТЗ-ME-01 / ADR-046) — K1-compliant: contracts + stdlib only.

Memory Evolution is the MECHANISM of Self-Evolving (round 2): it turns experience
(episodes) into consolidated SOFT-layer knowledge (semantic facts / soft policies),
deprecates low-confidence or outdated knowledge (forgetting), and manages normative
lifecycle (active / deprecated / superseded).

CRITICAL INVARIANT (O1, round 2): evolution is SOFT-only. The HARD layer — kernel
contracts, KROFT Laws, core FSM invariants — does NOT evolve from experience. The
Self-Evolving guard is enforced here: any proposed rule that fails
`IValueSystem.hard_violations` is REJECTED and never reaches the Normative layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple

from contracts.cognitive_domain import Episode, Policy, SemanticFact


class IMemoryEvolution(ABC):
    """Proposes + applies memory evolution from experience (ТЗ-ME-01, ADR-046).

    The engine is deterministic (LLM-free, I-09). It does NOT write memory directly
    (I-14): it returns proposals; the kernel routes them through ILayeredMemory with
    the Self-Evolving guard applied before commit.
    """

    @abstractmethod
    def consolidate(self, episodes: List[Episode]) -> Tuple[List[SemanticFact], List[Policy]]:
        """From episodes, propose consolidated SOFT knowledge.

        Returns (semantic_facts, soft_policies). Only repeated high-confidence episodes
        consolidate; low-confidence / single episodes are NOT proposed. Hard policies
        are NEVER produced here (O1). This method does NOT itself apply the guard — the
        kernel re-checks hard_violations before commit (defence in depth).
        """

    @abstractmethod
    def forget(self, episodes: List[Episode]) -> List[str]:
        """Return episode ids to deprecate (low-confidence / outdated / stale)."""

    @abstractmethod
    def supersede(self, old_policy_id: str, new_policy_id: str) -> None:
        """Record that `new_policy_id` supersedes `old_policy_id` (lifecycle update)."""

    @abstractmethod
    def consolidation_sidecar(self, episodes: List[Episode]) -> Dict[str, List[str]]:
        """ADR-028 Stage 2: abstraction sidecar.

        Returns a mapping ``fact_id -> [source episode ids]`` for the SAME
        consolidation that `consolidate` would produce, WITHOUT mutating any
        state. The returned mapping is persisted as a SEPARATE snapshot layer
        (abstraction_sidecar) so a fact can always be traced back to the exact
        episodes it was formed from — compression without loss (proof-over-existence).
        Deterministic (I-09): identical input -> identical mapping.
        """
