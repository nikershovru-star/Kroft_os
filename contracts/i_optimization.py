"""(contracts) IOptimizer / IGuardrail — Optimization Platform ports
(Wave 13, ADR-016).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Definition of Done (Roadmap Wave 13):

    No change is applied automatically without a rollback path.

Wave 13 turns Wave 12 `Pattern`s into `Recommendation`s, classifies risk via a
`Guardrail`, and applies config only through an explicit two-phase commit
(propose -> approve -> apply -> rollback). The guardrail CLASSIFIES; it never
mutates runtime state.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, List, Optional

from contracts.i_learning import ExecutionTrace, Pattern


# Status lifecycle (copy-on-write via new Recommendation, never in-place mutation)
REC_STATUS_PROPOSED = "proposed"
REC_STATUS_SHADOW = "shadow"
REC_STATUS_CANARY = "canary"
REC_STATUS_APPROVED = "approved"
REC_STATUS_APPLIED = "applied"
REC_STATUS_ROLLED_BACK = "rolled_back"
REC_STATUS_ALL = (
    REC_STATUS_PROPOSED, REC_STATUS_SHADOW, REC_STATUS_CANARY,
    REC_STATUS_APPROVED, REC_STATUS_APPLIED, REC_STATUS_ROLLED_BACK,
)

# Guardrail stages
GUARD_SHADOW = "shadow"
GUARD_CANARY = "canary"
GUARD_APPROVED = "approved"


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Recommendation:
    """A proposed change to a configuration path (ADR-016 §2, LAW 4).

    `target` is a STRING PATH (not a live pointer) so recommendations stay
    serialisable and safe: "policy:ProviderSelectionPolicy:weights:reasoning".
    `value` is the new value, JSON-encoded as a string.
    `source_pattern` references the Wave 12 `Pattern` that motivated this rec —
    see ADR-016 §"Отклонения": Pattern has no `id` field, so this is a string
    (its description or a normalised key).
    """

    id: str
    target: str
    value: str
    rationale: str
    confidence: float  # 0.0–1.0, carried from Pattern.confidence
    source_pattern: str
    status: str = REC_STATUS_PROPOSED


@dataclass(frozen=True)
class GuardrailResult:
    """Classification of a recommendation's risk (ADR-016 §2).

    The guardrail ONLY classifies — it does not mutate anything. `allowed` is
    True when the stage is shippable (approved/canary), False for shadow.
    """

    allowed: bool
    stage: str  # shadow | canary | approved
    risk_score: float  # 0.0–1.0
    explanation: str


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IOptimizer(abc.ABC):
    """Turn Wave 12 Patterns into Recommendations (ADR-016 §2)."""

    @abc.abstractmethod
    def recommend(
        self, patterns: List[Pattern], current_config: Dict
    ) -> List[Recommendation]:
        """Emit recommendations from patterns + current config.

        Must NOT apply anything — only propose (LAW 4/LAW 5).
        """
        raise NotImplementedError


class IGuardrail(abc.ABC):
    """Classify a recommendation's risk before any apply (ADR-016 §2)."""

    @abc.abstractmethod
    def validate(
        self, rec: Recommendation, traces: List[ExecutionTrace]
    ) -> GuardrailResult:
        """Return the risk classification for `rec`. Never mutates state."""
        raise NotImplementedError
