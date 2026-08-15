"""Self-Evolution Cycle — NEW internal mechanisms (CORE SELF-EVOLUTION WAVE).

K1-compliant: stdlib + contracts only. No service/adapter/runtime imports.

Implements the reference behaviors for the new ports defined in
``contracts/i_self_evolution_cycle.py``:

  STEP 3  Self-Observer       -> InMemoryKernelObserver (structured per-cycle record)
  STEP 5  Self-Evaluator      -> ReferenceSelfEvaluator (before/after/delta/regression)
  STEP 6  Capability Manager  -> ReferenceCapabilityManager (registry + gap detection)
  STEP 7  Hypothesis Engine   -> ReferenceHypothesisEngine (gap->hypothesis, not random)
  STEP 8  Experiment Engine   -> ReferenceExperimentEngine (sandbox baseline/candidate)
  STEP 11 Knowledge Boundary  -> ReferenceKnowledgeBoundary (KNOWN..UNKNOWN + abstain)

These EXTEND existing mechanisms (K3):
  - Self-Observer does NOT replace _outcomes; it adds structured state on top.
  - Self-Evaluator does NOT replace MemoryEvolution.consolidate; it is the
    measurement step that feeds the Evolution Controller's accept/reject decision.
  - Hypothesis Engine does NOT replace SkillEvolver.propose_improvement; it produces
    a GOAL-DIRECTED hypothesis from a capability gap, which the Evolution Controller
    may hand to SkillEvolver for the actual skill mutation.
  - Experiment Engine does NOT replace SkillEvolver's sandbox; it wraps a controlled
    baseline/candidate comparison around it.
  - Knowledge Boundary does NOT replace ConfidenceScore; it classifies a confidence
    into an epistemic state and gates action (do-not-pretend).
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from contracts.cognitive_domain import ConfidenceScore, NodeLamportClock, ProvenanceType
from contracts.i_self_evolution_cycle import (
    CapabilityGap,
    EvaluationResult,
    EvolutionHypothesis,
    Experiment,
    ICapabilityManager,
    IExperimentEngine,
    IHypothesisEngine,
    IKernelObserver,
    IKnowledgeBoundary,
    ISelfEvaluator,
    KnowledgeState,
    SelfObservationRecord,
)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# STEP 3 — Self-Observer (extends existing outcome logging)
# ---------------------------------------------------------------------------

class InMemoryKernelObserver(IKernelObserver):
    """Records structured per-cycle self-observations (called from inside tick).

    The kernel still appends ExecutionOutcome to ``_outcomes`` (existing). This
    observer ADDS the structured FSM/error/retrieval/learning view — it is a
    side-channel record, never a separate runtime.
    """

    def __init__(self) -> None:
        self._records: List[SelfObservationRecord] = []

    def observe_cycle(self, record: SelfObservationRecord) -> None:
        self._records.append(record)

    def recent(self, n: int = 10) -> List[SelfObservationRecord]:
        return list(self._records[-n:])

    def repeated_failures(self, episode_id: str) -> int:
        return sum(1 for r in self._records if r.episode_id == episode_id and not r.result)


# ---------------------------------------------------------------------------
# STEP 5 — Self-Evaluator (before/after measurement)
# ---------------------------------------------------------------------------

class ReferenceSelfEvaluator(ISelfEvaluator):
    """Before/after comparison with explicit delta + regression flag."""

    def evaluate(self, baseline: float, candidate: float,
                 metric: str, threshold: float) -> EvaluationResult:
        delta = round(candidate - baseline, 4)
        regression = delta < 0.0
        # success when candidate meets/exceeds the acceptance threshold over baseline
        success = (candidate - baseline) >= threshold
        conf = ConfidenceScore(
            round(min(1.0, 0.5 + abs(delta)), 3), ProvenanceType.RULE_INFERENCE)
        return EvaluationResult(
            success=success,
            score_before=round(baseline, 4),
            score_after=round(candidate, 4),
            delta=delta,
            regression=regression,
            confidence=conf,
            evidence=f"{metric}: {baseline:.3f} -> {candidate:.3f} (Δ={delta:+.3f}, thr={threshold})",
        )


# ---------------------------------------------------------------------------
# STEP 6 — Capability Manager (registry + gap detection)
# ---------------------------------------------------------------------------

class ReferenceCapabilityManager(ICapabilityManager):
    """Maintains a capability registry: actual score vs target, detects gaps."""

    def __init__(self) -> None:
        self._scores: Dict[str, float] = {}
        self._targets: Dict[str, float] = {}

    def register(self, name: str, score: float, target: float = 1.0) -> None:
        self._scores[name] = float(score)
        self._targets[name] = float(target)

    def score_of(self, name: str) -> Optional[float]:
        return self._scores.get(name)

    def detect_gaps(self) -> List[CapabilityGap]:
        gaps: List[CapabilityGap] = []
        for name, score in self._scores.items():
            target = self._targets.get(name, 1.0)
            gap = round(target - score, 4)
            if gap > 0.0:
                status = "missing" if score < 0.2 else ("bad" if score < 0.5 else "degraded")
                gaps.append(CapabilityGap(
                    name=name, status=status, score=score, target=target,
                    gap=gap, evidence=f"{name} score={score:.2f} < target={target:.2f}"))
        # worst gap first
        gaps.sort(key=lambda g: g.gap, reverse=True)
        return gaps


# ---------------------------------------------------------------------------
# STEP 7 — Hypothesis Engine (goal-directed, from gap, not random)
# ---------------------------------------------------------------------------

class ReferenceHypothesisEngine(IHypothesisEngine):
    """Formulates an EvolutionHypothesis from a capability gap + evidence.

    Replaces the "drop longest step" heuristic of SkillEvolver with a reasoned
    proposal: the change is derived from the gap's nature (e.g. degraded retrieval
    -> increase semantic contribution), and carries an explicit acceptance threshold.
    """

    # simple, inspectable cause->change map (deterministic, extensible)
    _CAUSE_CHANGE = {
        "retrieval": "increase semantic contribution during hybrid ranking",
        "planning": "bias planning toward higher-value candidates using past outcomes",
        "execution": "prefer the action variant with the best historical success rate",
        "reasoning": "surface consolidated facts earlier in deliberation",
        "learning": "raise consolidation confidence threshold to reduce noise",
    }

    def formulate(self, gap: CapabilityGap, evidence: str,
                  suspected_cause: str) -> Optional[EvolutionHypothesis]:
        if gap.gap <= 0.0:
            return None  # no gap -> no hypothesis
        change = self._CAUSE_CHANGE.get(gap.name, f"improve {gap.name} behavior")
        expected = f"{gap.name} score {gap.score:.2f} -> >= {gap.target:.2f}"
        return EvolutionHypothesis(
            id=_uid("hyp"),
            problem=f"{gap.name} underperforms (score={gap.score:.2f}, target={gap.target:.2f})",
            evidence=evidence or gap.evidence,
            suspected_cause=suspected_cause or f"{gap.name} capability below target",
            proposed_change=change,
            expected_effect=expected,
            metric=gap.name,
            acceptance_threshold=round(min(0.1, gap.gap * 0.5), 3),
        )


# ---------------------------------------------------------------------------
# STEP 8 — Experiment Engine (controlled baseline/candidate)
# ---------------------------------------------------------------------------

class ReferenceExperimentEngine(IExperimentEngine):
    """Runs a controlled baseline-vs-candidate experiment in a sandbox.

    Does NOT mutate production. Measures the candidate via an injected scorer
    (e.g. SkillEvolver sandbox or a metric function) and compares to baseline +
    threshold. Returns an Experiment; the Evolution Controller decides promotion.
    """

    def __init__(self, scorer=None) -> None:
        # scorer: callable(candidate_description: str) -> float  (sandbox). Optional.
        self._scorer = scorer

    def run(self, hypothesis: EvolutionHypothesis, baseline: float) -> Experiment:
        candidate = 0.0
        if self._scorer is not None:
            try:
                candidate = float(self._scorer(hypothesis.proposed_change))
            except Exception:
                candidate = baseline  # safe fallback: never credit a failed experiment
        promoted = (candidate - baseline) >= hypothesis.acceptance_threshold
        return Experiment(
            id=_uid("exp"),
            hypothesis_id=hypothesis.id,
            baseline=round(baseline, 4),
            candidate=round(candidate, 4),
            metric=hypothesis.metric,
            threshold=hypothesis.acceptance_threshold,
            result=round(candidate, 4),
            promoted=promoted,
        )


# ---------------------------------------------------------------------------
# STEP 11 — Knowledge Boundary (epistemic state + do-not-pretend)
# ---------------------------------------------------------------------------

class ReferenceKnowledgeBoundary(IKnowledgeBoundary):
    """Classifies confidence/evidence into an epistemic state and gates action.

    Distinct from a raw ConfidenceScore: a high-confidence guess with NO evidence is
    still UNCERTAIN. The kernel must ABSTAIN (not act / not invent) when UNKNOWN.
    """

    def classify(self, confidence: float, evidence_strength: float) -> KnowledgeState:
        if confidence < 0.3 or evidence_strength < 0.2:
            return KnowledgeState.UNKNOWN
        if confidence < 0.55 or evidence_strength < 0.5:
            return KnowledgeState.UNCERTAIN
        if confidence < 0.8:
            return KnowledgeState.LIKELY
        return KnowledgeState.KNOWN

    def should_abstain(self, state: KnowledgeState) -> bool:
        return state in (KnowledgeState.UNKNOWN, KnowledgeState.UNCERTAIN)
