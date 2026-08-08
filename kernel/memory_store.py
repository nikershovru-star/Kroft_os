"""In-memory ILayeredMemory implementation (ТЗ-ME-01) — K1-compliant.

Two-layer memory: episode (raw) + normative (rules/ADR) + SOFT semantic layer
(consolidated facts). Write routing by layer is enforced here so Learning NEVER
writes memory directly (I-14). Normative lifecycle (deprecate / supersede) enforces
the O1 Self-Evolving guard: HARD policies are immutable from experience.
"""

from __future__ import annotations

from typing import List, Optional

from contracts.cognitive_domain import Episode, Policy, PolicyLifecycle, SemanticFact
from contracts.i_cognitive_kernel import ILayeredMemory


class InMemoryLayeredMemory(ILayeredMemory):
    def __init__(self) -> None:
        self._episodes: List[Episode] = []
        self._normative: List[Policy] = []
        self._semantic: List[SemanticFact] = []
        # Optional hook fired after each record_episode (e.g. embedding-cache
        # invalidation in CognitiveKernel). None = no-op. K5: impl-only extension.
        self.on_record_episode = None

    def record_episode(self, episode: Episode) -> None:
        self._episodes.append(episode)
        if self.on_record_episode is not None:
            self.on_record_episode()

    def commit_normative(self, policy: Policy) -> None:
        self._normative.append(policy)

    def get_episodes(self) -> List[Episode]:
        return list(self._episodes)

    def commit_semantic(self, fact: SemanticFact) -> None:
        self._semantic.append(fact)

    def get_semantic(self) -> List[SemanticFact]:
        return list(self._semantic)

    def get_normative(self) -> List[Policy]:
        return list(self._normative)

    def deprecate_normative(self, policy_id: str,
                            superseded_by: Optional[str] = None) -> None:
        for p in self._normative:
            if p.id == policy_id:
                if p.layer == "hard":
                    # O1 guard: HARD layer is immutable from experience (Self-Evolving)
                    raise RuntimeError(f"cannot deprecate HARD policy {policy_id} (O1)")
                new_lc = PolicyLifecycle.SUPERSEDED if superseded_by else PolicyLifecycle.DEPRECATED
                object.__setattr__(p, "lifecycle", new_lc)
