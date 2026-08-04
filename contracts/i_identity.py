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

    Deterministic: trust_score_of(author_id) returns a stable aggregate (MAX of recorded
    scores) used for FEDERATION gating; threshold_check is a pure comparison. Default
    gating is PERMISSIVE (caller supplies threshold).

    ТЗ-ORCH-01 extension: ``record_outcome`` / ``current_trust`` maintain a LATEST running
    score that EVOLVES from dispatch outcomes (success raises, failure lowers). This is the
    value the orchestrator routes on — distinct from the MAX aggregate used for federation,
    which closes Флаг 1 (trust-then-attack) of IDT-01: a single high item no longer makes an
    author permanently trusted, because the orchestrator reads ``current_trust`` (latest),
    not ``trust_score_of`` (max).
    """

    def record(self, meta: TrustMeta) -> None:
        raise NotImplementedError

    def get(self, item_id: str) -> Optional[TrustMeta]:
        raise NotImplementedError

    def trust_score_of(self, author_id: str) -> float:
        """Aggregate trust for an author (MAX of recorded scores; 0.0 if unknown).

        Used for FEDERATION gating. Deterministic.
        """
        raise NotImplementedError

    def threshold_check(self, meta: TrustMeta, threshold: float) -> bool:
        """True if ``meta.trust_score >= threshold`` (and author known)."""
        raise NotImplementedError

    def record_outcome(self, author_id: str, success: bool, delta: float = 0.1) -> float:
        """Update the LATEST running trust from a dispatch outcome; return the new score.

        Deterministic: success -> +delta (capped at 1.0), failure -> -delta (floored at 0.0).
        Unknown author starts from 0.5. The orchestrator calls this to evolve trust.
        """
        raise NotImplementedError

    def current_trust(self, author_id: str) -> float:
        """LATEST running trust for an author (0.5 if no outcome recorded yet).

        Distinct from ``trust_score_of`` (MAX of recorded ``TrustMeta`` scores). The
        orchestrator routes on ``current_trust`` so a failure actually lowers trust.
        """
        raise NotImplementedError

    def seed(self, author_id: str, score: float) -> None:
        """Set the LATEST running trust baseline (e.g. from AgentIdentity.trust_level).

        Idempotent: does NOT overwrite a score already evolved by ``record_outcome``.
        Called by the orchestrator at build time to initialise running trust from the
        declared identity trust; subsequent dispatch outcomes evolve it.
        """
        raise NotImplementedError


class IActionLog:
    """Append-only log of actions per agent (ТЗ-IDT-01). Audit/rollback surface."""

    def append(self, agent_id: str, action: str) -> None:
        raise NotImplementedError

    def list(self, agent_id: str) -> List[str]:
        raise NotImplementedError
