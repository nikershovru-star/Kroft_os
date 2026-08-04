"""Reference Identity & Trust registries (ТЗ-IDT-01, ADR-072) — deterministic, LLM-free.

K1-compliant: stdlib + contracts only. Reference in-memory implementations:
- ReferenceIdentityRegistry: stable agent identities (one-port-per-boundary vs AgentState).
- ReferenceTrustRegistry: deterministic trust bookkeeping (record/get/trust_score_of/
  threshold_check). trust_score_of aggregates the MAX recorded trust_score per author
  (deterministic, monotone-friendly for rollback: higher version wins on tie via max-score).
- ReferenceActionLog: append-only per-agent log (audit/rollback surface).

O1: these registries only READ/WRITE their own state; they never mutate HARD/FSM/contracts.
I-09: all operations deterministic for a given input sequence.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from contracts.i_identity import (
    AgentIdentity,
    IActionLog,
    IIdentityRegistry,
    ITrustRegistry,
    TrustMeta,
)


class ReferenceIdentityRegistry(IIdentityRegistry):
    """In-memory registry of stable agent identities."""

    def __init__(self) -> None:
        self._agents: Dict[str, AgentIdentity] = {}

    def register(self, identity: AgentIdentity) -> None:
        self._agents[identity.agent_id] = identity

    def get(self, agent_id: str) -> Optional[AgentIdentity]:
        return self._agents.get(agent_id)

    def list(self) -> List[AgentIdentity]:
        return [self._agents[k] for k in sorted(self._agents)]

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents


class ReferenceTrustRegistry(ITrustRegistry):
    """In-memory deterministic trust registry.

    trust_score_of aggregates per author: the highest trust_score among recorded items
    for that author (deterministic). Unknown author -> 0.0. threshold_check is pure.
    """

    def __init__(self) -> None:
        self._by_item: Dict[str, TrustMeta] = {}
        self._by_author: Dict[str, List[TrustMeta]] = {}
        # ТЗ-ORCH-01: LATEST running trust per author (evolves from dispatch outcomes).
        # Distinct from the MAX aggregate (_by_author scores used for federation gating).
        self._running: Dict[str, float] = {}

    def record(self, meta: TrustMeta) -> None:
        self._by_item[meta.item_id] = meta
        self._by_author.setdefault(meta.author_id, []).append(meta)

    def get(self, item_id: str) -> Optional[TrustMeta]:
        return self._by_item.get(item_id)

    def trust_score_of(self, author_id: str) -> float:
        items = self._by_author.get(author_id)
        if not items:
            return 0.0
        # deterministic aggregate: max recorded trust_score for this author
        return max(it.trust_score for it in items)

    def threshold_check(self, meta: TrustMeta, threshold: float) -> bool:
        return meta.trust_score >= threshold

    def record_outcome(self, author_id: str, success: bool, delta: float = 0.1) -> float:
        """Evolve LATEST running trust: success +delta (cap 1.0), failure -delta (floor 0.0)."""
        cur = self._running.get(author_id, 0.5)
        cur = cur + delta if success else cur - delta
        cur = max(0.0, min(1.0, cur))
        self._running[author_id] = cur
        return cur

    def current_trust(self, author_id: str) -> float:
        """LATEST running trust (0.5 if no outcome recorded yet)."""
        return self._running.get(author_id, 0.5)

    def seed(self, author_id: str, score: float) -> None:
        if author_id not in self._running:
            self._running[author_id] = max(0.0, min(1.0, score))


class ReferenceActionLog(IActionLog):
    """Append-only per-agent action log."""

    def __init__(self) -> None:
        self._log: Dict[str, List[str]] = {}

    def append(self, agent_id: str, action: str) -> None:
        self._log.setdefault(agent_id, []).append(action)

    def list(self, agent_id: str) -> List[str]:
        return list(self._log.get(agent_id, ()))
