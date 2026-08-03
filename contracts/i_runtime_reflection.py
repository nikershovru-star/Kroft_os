"""Runtime / System Reflection contracts (ТЗ-RT-01, ADR-062).

K1-compliant: stdlib + contracts only. LLM-FREE core (Round 2 adaptive runtime).

Separation from RF-01 (cognitive reflection):
- RF-01 reflects on COGNITIVE EXPERIENCE -> evolves SOFT *content* (semantic facts,
  soft policies). It NEVER tunes operational parameters.
- RT-01 (this module) reflects on OPERATIONAL METRICS (delivery rates, latencies,
  memory growth) -> proposes TUNING of SOFT *runtime parameters* (timeouts, thresholds,
  budgets). It NEVER writes semantic/policy content (that is RF-01 + ME-01).

O1 Self-Evolving guard (round 2): runtime reflection tunes ONLY SOFT runtime
parameters. FSM invariants, HARD policies, contracts, kernel structure are IMMUTABLE.
`ITuningApplier.apply` MUST reject any proposal whose `layer` is not "SOFT" or whose
`param` is not in the allowed SOFT set — this is the mechanical O1 enforcement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    Provenance,
    ProvenanceType,
)


class TuningLayer(str, Enum):
    """Which layer a tuning proposal targets. O1: only SOFT is mutable."""
    SOFT = "SOFT"      # runtime tunables: timeouts, thresholds, budgets
    HARD = "HARD"      # FSM invariants / HARD policies / contracts — IMMUTABLE


@dataclass(frozen=True)
class RuntimeMetric:
    """An operational metric sample observed by the runtime (NOT cognitive content).

    SOFT-only by nature: it describes *how the system runs*, not *what it knows*.
    Carries ConfidenceScore + CausalMark for the same provenance discipline as the
    cognitive layer (ADR-055 / ТЗ-CAUSAL-01).
    """
    name: str
    value: float
    confidence: ConfidenceScore
    causal: CausalMark = field(default_factory=lambda: CausalMark("runtime", 0))
    provenance: Provenance = field(
        default_factory=lambda: Provenance(source="runtime", actor="runtime"))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RuntimeMetric.name must be non-empty")


@dataclass(frozen=True)
class TuningProposal:
    """A proposed change to a SOFT runtime parameter, derived from reflection.

    `old_value` / `new_value` are floats (numeric runtime tunables). `layer` MUST be
    SOFT for `ITuningApplier.apply` to accept it (O1 guard). `param` is the tunable
    key (e.g. "network.ensure_connected_timeout", "memory.min_repetitions").
    """
    param: str
    old_value: float
    new_value: float
    rationale: str
    confidence: ConfidenceScore
    causal: CausalMark = field(default_factory=lambda: CausalMark("runtime", 0))
    layer: TuningLayer = TuningLayer.SOFT

    def __post_init__(self) -> None:
        if not self.param:
            raise ValueError("TuningProposal.param must be non-empty")
        if self.layer == TuningLayer.HARD:
            # Hardened at construction: a HARD proposal is a design error if it
            # reaches the runtime at all. The applier still double-checks by layer.
            raise ValueError(
                "TuningProposal with layer=HARD is forbidden by O1 (Self-Evolving guard): "
                "FSM invariants / HARD policies / contracts are immutable")

    @property
    def is_soft(self) -> bool:
        return self.layer == TuningLayer.SOFT


class IRuntimeMetrics(ABC):
    """Collects operational runtime metrics for reflection (LLM-free)."""

    @abstractmethod
    def collect(self) -> List[RuntimeMetric]:
        """Return the current operational metric snapshot."""
        ...


class IRuntimeReflection(ABC):
    """Reflects on operational metrics and produces tuning proposals (LLM-free).

    Deterministic: a given metric pattern maps to a specific, reproducible proposal.
    Proposals target SOFT runtime parameters only (O1).
    """

    @abstractmethod
    def reflect(self, metrics: List[RuntimeMetric]) -> List[TuningProposal]:
        """Analyze metrics, detect operational patterns, return tuning proposals."""
        ...


class ITuningApplier(ABC):
    """Applies tuning proposals under the O1 Self-Evolving guard.

    Only SOFT runtime parameters in the `allowed_soft_params` set are mutated.
    A HARD-layer or non-allowed proposal is REJECTED (returns False / raises) — the
    runtime structure, FSM invariants, HARD policies and contracts stay immutable.
    """

    @abstractmethod
    def apply(self, proposal: TuningProposal) -> bool:
        """Apply `proposal` if SOFT + allowed; reject otherwise. Returns success."""
        ...

    @abstractmethod
    def allowed_params(self) -> Set[str]:
        """The set of SOFT runtime parameters this applier may tune."""
        ...
