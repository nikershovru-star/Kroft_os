"""Identity & Trust port (ТЗ-IDT-01, ADR-072).

K5 (commit 0): K5-разведка нашла, что порт Identity/Trust НЕ существовал. Смежные сущности
УЖЕ есть и переиспользуются, НЕ дублируются:
- ``AgentState`` (ТЗ-AGENT-001, contracts/agent_orchestration + kernel/agent_lifecycle) — это
  lifecycle-FSM агента, ДРУГАЯ граница (orchestration), НЕ identity/trust. НЕ дублируем.
- ``Provenance`` / ``CausalMark`` (contracts/cognitive_domain) — переиспользуются для trust-
  метаданных (author/version/provenance), НЕ дублируем.
- ``FederationSoftMemorySync`` (services/distributed_runtime.py, ТЗ-FSE-01) — федератует SOFT-
  слой БЕЗ trust-гейтинга (дыра). IDT-01 расширяет его ОПЦИОНАЛЬНЫМ gating (commit 3), НЕ
  дублируя.

IDT-01 вводит identity (агент как постоянный участник) + trust (trust-score/version/author/
rollback) + trust-гейтинг федерации. O1: identity/trust НЕ мутируют HARD/FSM/контракты.
Frozen VO с реальными типами (урок Флага 1 LLM-01). Детерминизм (I-09).

K1-compliant: stdlib + contracts only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class AgentIdentity:
    """Stable identity of an agent/participant (ТЗ-IDT-01).

    Distinct from ``AgentState`` (ТЗ-AGENT-001 lifecycle FSM): this is the persistent
    WHO (specialization, trust posture, permissions, memory handle), not the runtime FSM.
    """
    agent_id: str
    specialization: str
    trust_level: float                      # 0.0 .. 1.0 aggregate trust posture
    permissions: Tuple[str, ...] = ()
    memory_ref: Optional[str] = None        # optional handle into ILayeredMemory


@dataclass(frozen=True)
class TrustMeta:
    """Trust metadata attached to a federated item (ТЗ-IDT-01).

    ``trust_score`` is deterministic (set by the authoring node, recorded by receiver).
    ``version`` + ``rollback_pointer`` enable rollback; ``author_id`` enables per-author
    trust gating at the federation boundary.
    """
    item_id: str
    trust_score: float                      # 0.0 .. 1.0
    version: int
    author_id: str
    rollback_pointer: Optional[str] = None  # item_id of the prior version, if any


class IIdentityRegistry:
    """Registry of stable agent identities (ТЗ-IDT-01). One-port-per-boundary."""

    def register(self, identity: AgentIdentity) -> None:
        raise NotImplementedError

    def get(self, agent_id: str) -> Optional[AgentIdentity]:
        raise NotImplementedError

    def list(self) -> List[AgentIdentity]:
        raise NotImplementedError

    def has(self, agent_id: str) -> bool:
        raise NotImplementedError


class ITrustRegistry:
    """Trust bookkeeping for federated items (ТЗ-IDT-01).

    Deterministic: trust_score_of(author_id) returns a stable aggregate; threshold_check
    is a pure comparison. Default gating is PERMISSIVE (caller supplies threshold).
    """

    def record(self, meta: TrustMeta) -> None:
        raise NotImplementedError

    def get(self, item_id: str) -> Optional[TrustMeta]:
        raise NotImplementedError

    def trust_score_of(self, author_id: str) -> float:
        """Aggregate trust for an author (0.0 if unknown). Deterministic."""
        raise NotImplementedError

    def threshold_check(self, meta: TrustMeta, threshold: float) -> bool:
        """True if ``meta.trust_score >= threshold`` (and author known)."""
        raise NotImplementedError


class IActionLog:
    """Append-only log of actions per agent (ТЗ-IDT-01). Audit/rollback surface."""

    def append(self, agent_id: str, action: str) -> None:
        raise NotImplementedError

    def list(self, agent_id: str) -> List[str]:
        raise NotImplementedError
