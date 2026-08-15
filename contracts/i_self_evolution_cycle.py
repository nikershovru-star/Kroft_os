"""Self-Evolution Cycle contracts — NEW internal mechanism layer (CORE SELF-EVOLUTION WAVE).

K1-compliant: stdlib + contracts only. NO kernel/service/runtime imports.

WHY A NEW MODULE (K3 boundary check):
- ``contracts/i_knowledge.py`` already defines a ``Hypothesis`` — but that is a
  KNOWLEDGE-GRAPH hypothesis (subject-predicate-object triple for graph validation,
  ADR-011). It is a DIFFERENT concept from an EVOLUTION hypothesis (a proposed
  behavior change to improve the kernel itself). We do NOT reuse/rename it; we
  define ``EvolutionHypothesis`` here to avoid any collision or confusion.
- ``SkillEvolver`` / ``IMemoryEvolution`` already own skill + SOFT-layer evolution.
  This module does NOT duplicate them: it defines the CAUSAL + CAPABILITY + EXPERIMENT
  vocabulary that feeds *into* those existing writers (STEP 9: Evolution Controller
  reuses SkillEvolver / IMemoryEvolution — it does not create a second one).

Scope of VOs defined here:
- ``CausalEvent``     : attribution record (change -> outcome), NOT a CausalMark
                        (CausalMark = event ordering/origin; CausalEvent = attribution).
- ``EvaluationResult`` : before/after/score/delta/regression.
- ``CapabilityGap``    : what the OS can/can't do, target vs actual.
- ``EvolutionHypothesis`` : proposed change + expected effect + acceptance threshold.
- ``Experiment``      : baseline vs candidate controlled run + result.

Ports:
- ``ICausalAnalyzer``   : answers "did change X cause outcome Y?"
- ``ISelfEvaluator``    : before/after comparison of a behavior change.
- ``ICapabilityManager`` : maintains the capability registry + gap detection.
- ``IHypothesisEngine``  : turns (observation, causal, gap) into an EvolutionHypothesis.
- ``IExperimentEngine``  : runs a controlled baseline/candidate experiment (sandbox).
- ``IKernelObserver``    : structured self-observation of the running cycle (extends existing).
- ``IKnowledgeBoundary`` : KNOWN/LIKELY/UNCERTAIN/UNKNOWN + do-not-pretend gate.

All deterministic (I-09) where possible; LLM is an optional non-blocking advisor only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from contracts.cognitive_domain import ConfidenceScore, NodeLamportClock, Provenance


# ---------------------------------------------------------------------------
# Value Objects (frozen where possible — LAW 3: no hidden mutable state)
# ---------------------------------------------------------------------------

class KnowledgeState(str, Enum):
    """Knowledge Boundary levels (STEP 11). Distinct from confidence magnitude."""
    KNOWN = "known"
    LIKELY = "likely"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CausalEvent:
    """Attribution record: a specific CHANGE and the OUTCOME it produced.

    NOT a CausalMark. CausalMark (cognitive_domain) records event ORDERING and
    ORIGIN (Lamport clock, node_id) — it does NOT assert that change X *caused*
    outcome Y. CausalEvent is the attribution layer on top of that ordering.
    """
    event_id: str
    episode_id: str
    parent_event_id: Optional[str]
    change: str                 # what was changed (e.g. "skill v1 -> v2: dropped step")
    hypothesis_id: Optional[str]
    action: str
    observation: str
    outcome: str                # textual outcome summary
    success: bool
    confidence: ConfidenceScore
    timestamp: float


@dataclass(frozen=True)
class EvaluationResult:
    """Before/after structured evaluation of a behavior change (STEP 5)."""
    success: bool
    score_before: float
    score_after: float
    delta: float
    regression: bool
    confidence: ConfidenceScore
    evidence: str


@dataclass(frozen=True)
class CapabilityGap:
    """A detected gap between actual and target capability (STEP 6)."""
    name: str                   # e.g. "retrieval"
    status: str                 # "ok" | "degraded" | "missing" | "bad"
    score: float
    target: float
    gap: float                  # target - score (negative => over target)
    evidence: str


@dataclass(frozen=True)
class EvolutionHypothesis:
    """A proposed behavior change with an expected, measurable effect (STEP 7).

    Distinct from knowledge-graph Hypothesis (i_knowledge.Hypothesis): this is about
    improving the KERNEL's own behavior, not ingesting a fact into the knowledge graph.
    """
    id: str
    problem: str
    evidence: str
    suspected_cause: str
    proposed_change: str
    expected_effect: str
    metric: str                 # e.g. "R@5" | "execution_success_rate"
    acceptance_threshold: float  # min delta to accept


@dataclass(frozen=True)
class Experiment:
    """A controlled baseline-vs-candidate experiment (STEP 8)."""
    id: str
    hypothesis_id: str
    baseline: float
    candidate: float
    metric: str
    threshold: float
    result: Optional[float] = None       # measured candidate score
    promoted: bool = False


# ---------------------------------------------------------------------------
# Ports (K1-clean, kernel-importable)
# ---------------------------------------------------------------------------

class IKernelObserver(ABC):
    """Structured self-observation of a running cycle (STEP 3).

    Extends the EXISTING outcome-logging: the kernel already appends
    ExecutionOutcome to ``_outcomes``. This port adds structured per-cycle state
    (fsm transitions, errors, retries, thrash, retrieval/reasoning/learning quality)
    WITHOUT becoming a separate runtime — it is called from inside tick().
    """

    @abstractmethod
    def observe_cycle(self, record: "SelfObservationRecord") -> None:
        """Record one structured self-observation (called from tick)."""


@dataclass
class SelfObservationRecord:
    """Payload the kernel emits on each cycle (STEP 3 minimal set)."""
    cycle_id: str
    episode_id: str
    fsm_state: str
    transition: str
    goal: str
    action: str
    result: str
    confidence: float
    errors: Tuple[str, ...] = ()
    tool_failures: Tuple[str, ...] = ()
    planning_failures: int = 0
    execution_failures: int = 0
    retrieval_quality: float = 0.0
    reasoning_outcome: str = ""
    learning_outcome: str = ""
    cycle_duration: float = 0.0
    retry_count: int = 0
    thrash_count: int = 0
    repeated_action: bool = False
    repeated_failure: bool = False


class ICausalAnalyzer(ABC):
    """Answers: did CHANGE X cause OUTCOME Y? (STEP 4)."""

    @abstractmethod
    def attribute(self, change: str, outcome_event: CausalEvent) -> CausalEvent:
        """Record + attribute an outcome to a change; returns the CausalEvent."""

    @abstractmethod
    def caused_improvement(self, event: CausalEvent) -> bool:
        """True if the attributed change is the likely cause of improvement."""


class ISelfEvaluator(ABC):
    """Before/after evaluation of a behavior change (STEP 5)."""

    @abstractmethod
    def evaluate(self, baseline: float, candidate: float,
                 metric: str, threshold: float) -> EvaluationResult:
        """Compare baseline vs candidate; flag regression if delta < 0."""


class ICapabilityManager(ABC):
    """Capability registry + gap detection (STEP 6)."""

    @abstractmethod
    def register(self, name: str, score: float, target: float = 1.0) -> None:
        """Record/refresh a capability's current score + target."""

    @abstractmethod
    def detect_gaps(self) -> List[CapabilityGap]:
        """Return capabilities below target (gaps to drive hypothesis)."""


class IHypothesisEngine(ABC):
    """Turns (observation, causal, gap) into an EvolutionHypothesis (STEP 7)."""

    @abstractmethod
    def formulate(self, gap: CapabilityGap, evidence: str,
                  suspected_cause: str) -> Optional[EvolutionHypothesis]:
        """Propose a goal-directed, evidence-based hypothesis (not random)."""


class IExperimentEngine(ABC):
    """Controlled baseline/candidate experiment (STEP 8).

    MUST NOT mutate production — runs in sandbox only; the Evolution Controller
    decides promotion AFTER the experiment returns.
    """

    @abstractmethod
    def run(self, hypothesis: EvolutionHypothesis,
            baseline: float) -> Experiment:
        """Run candidate in sandbox, measure, compare to baseline + threshold."""


class IKnowledgeBoundary(ABC):
    """Knowledge Boundary gate (STEP 11): distinguish KNOWN..UNKNOWN + do-not-pretend."""

    @abstractmethod
    def classify(self, confidence: float, evidence_strength: float) -> KnowledgeState:
        """Map a confidence/evidence pair to a KnowledgeState."""

    @abstractmethod
    def should_abstain(self, state: KnowledgeState) -> bool:
        """True when the kernel must abstain instead of acting on insufficient evidence."""
