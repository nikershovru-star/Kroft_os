"""IPolicy — Policy Platform port (Wave 5, ADR-009).

Policy as Code: each policy is a class implementing this contract; the
PolicyEngine orchestrates without knowing rule semantics.

Adapters may import contracts + stdlib only. Domain (kernel, services, policies)
depends on this interface, never on concrete providers. Policies depend only on
ModelRegistry + contracts (never on adapters).

Phase A of ADR-009. No implementation here — only ports.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from contracts.i_llm import ModelInfo, ModelQuery


@dataclass
class CallRecord:
    """Lightweight snapshot of a past call (ADR-009 §3.1)."""
    model: str
    tokens: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    timestamp: float = 0.0


@dataclass(frozen=True)
class PolicyContext:
    """Immutable snapshot of the world at decision time (ADR-009 §3.1)."""
    query: ModelQuery
    user_id: str = "default"
    session_id: str = ""
    history: List[CallRecord] = field(default_factory=list)
    estimated_cost: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    """Result of a policy evaluation (ADR-009 §3.2)."""
    allowed: bool
    selected_model: Optional[ModelInfo] = None
    fallback_chain: List[ModelInfo] = field(default_factory=list)
    reason: str = ""
    audit_log: List[str] = field(default_factory=list)
    constraints_applied: List[str] = field(default_factory=list)
    vetoed_by: Optional[str] = None


class IPolicy(abc.ABC):
    """A single policy. Does NOT choose the model itself — it filters the
    catalog and scores surviving candidates; the engine makes the final pick."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique policy name."""
        raise NotImplementedError

    @property
    def priority(self) -> int:
        """Evaluation order; lower runs earlier. Default 100."""
        return 100

    @property
    def can_veto(self) -> bool:
        """May this policy fully block the request?"""
        return False

    @abc.abstractmethod
    def evaluate(self, context: PolicyContext, catalog: List[ModelInfo]) -> PolicyDecision:
        """Evaluate context against the model catalog.

        Returns a Decision. The engine merges decisions across policies.
        A non-veto policy should return allowed=True with the surviving/filtered
        catalog carried in `fallback_chain` and may bump `selected_model` for ranking.
        """
        raise NotImplementedError
