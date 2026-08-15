"""Self-Evolution Controller — COORDINATOR (CORE SELF-EVOLUTION WAVE, STEP 9/10).

K1-compliant: stdlib + contracts only. No service/adapter/runtime imports.

CRITICAL (K9 / STEP 9): this is NOT a second evolution controller. It COORDINATES
the new self-observation -> causal -> capability -> hypothesis -> experiment chain
and delegates the ACTUAL mutation to the EXISTING writers:

  - skill mutation      -> ``ISkillEvolver``  (services/skill_evolution.py, ТЗ-EVOLUTION-01)
  - SOFT-layer learning -> ``IMemoryEvolution`` (kernel/memory_evolution.py, ТЗ-ME-01)

The Controller only ACCEPTS/REJECTS/ROLLS-BACK based on the experiment + evaluation
result, never inventing its own persistence. Rollback = keep the previous procedure
version (SkillEvolver already marks old as SUPERSEDED, never deletes — O1).

Closed loop inside the kernel:
  experience -> observe -> causal -> capability gap -> hypothesis
            -> experiment -> evaluate -> accept/reject -> memory -> next cycle
"""

from __future__ import annotations

from typing import List, Optional

from contracts.cognitive_domain import ConfidenceScore, NodeLamportClock, ProvenanceType
from contracts.i_self_evolution_cycle import (
    CapabilityGap,
    CausalEvent,
    EvaluationResult,
    EvolutionHypothesis,
    Experiment,
    ICausalAnalyzer,
    ICapabilityManager,
    IExperimentEngine,
    IHypothesisEngine,
    IKernelObserver,
    ISelfEvaluator,
    SelfObservationRecord,
)


class SelfEvolutionController:
    """Coordinates the self-evolution cycle; delegates mutation to existing writers.

    All sub-components are INJECTED (K6: via ports, never imported concrete). The
    kernel wires them in KernelBuilder. Missing sub-components -> the cycle is a
    no-op (backward compatible, like evolution-disabled today).
    """

    def __init__(self,
                 clock: Optional[NodeLamportClock] = None,
                 observer: Optional[IKernelObserver] = None,
                 causal: Optional[ICausalAnalyzer] = None,
                 capability: Optional[ICapabilityManager] = None,
                 hypothesis: Optional[IHypothesisEngine] = None,
                 experiment: Optional[IExperimentEngine] = None,
                 evaluator: Optional[ISelfEvaluator] = None,
                 # existing writers (delegated mutation):
                 skill_evolver=None,
                 memory_evolution=None,
                 # optional persistence for evolution history (reuses ILayeredMemory)
                 memory=None) -> None:
        self._clock = clock
        self._observer = observer
        self._causal = causal
        self._capability = capability
        self._hypothesis = hypothesis
        self._experiment = experiment
        self._evaluator = evaluator
        self._skill_evolver = skill_evolver
        self._memory_evolution = memory_evolution
        self._memory = memory
        # evolution history (survives in-memory; persisted via persist() -> SOFT layer)
        self._hypothesis_history: List[EvolutionHypothesis] = []
        self._experiment_history: List[Experiment] = []
        self._accepted: List[str] = []
        self._rejected: List[str] = []

    # -- STEP 13/14: persist evolution history through EXISTING contract -----
    def persist(self) -> None:
        """Persist capability + evolution history via the EXISTING ILayeredMemory
        SOFT layer (same contract Memory Evolution uses). Never writes a new
        snapshot format; never mutates production outside this contract."""
        if self._memory is None or self._capability is None:
            return
        commit = getattr(self._memory, "commit_semantic", None)
        if commit is None:
            return
        from contracts.cognitive_domain import SemanticFact, ConfidenceScore, ProvenanceType
        for gap in self._capability.detect_gaps():
            try:
                commit(SemanticFact(
                    id=f"capgap:{gap.name}",
                    content=f"capability_gap:{gap.name}:score={gap.score:.2f}:target={gap.target:.2f}",
                    confidence=ConfidenceScore(0.6, ProvenanceType.REFLECTION),
                ))
            except Exception:
                pass  # persistence is best-effort; never break the loop

    def history(self):
        """Return (hypotheses, experiments, accepted, rejected) for introspection."""
        return (list(self._hypothesis_history), list(self._experiment_history),
                list(self._accepted), list(self._rejected))

    # -- STEP 3: self-observation ------------------------------------------
    def observe(self, record: SelfObservationRecord) -> None:
        if self._observer is not None:
            self._observer.observe_cycle(record)

    # -- STEP 4: causal attribution ----------------------------------------
    def attribute(self, change: str, event: CausalEvent) -> Optional[CausalEvent]:
        if self._causal is None:
            return None
        return self._causal.attribute(change, event)

    # -- STEP 6: capability gap -------------------------------------------
    def detect_gaps(self) -> List[CapabilityGap]:
        if self._capability is None:
            return []
        return self._capability.detect_gaps()

    # -- STEP 7: hypothesis from gap --------------------------------------
    def formulate(self, gap: CapabilityGap, evidence: str,
                  suspected_cause: str) -> Optional[EvolutionHypothesis]:
        if self._hypothesis is None:
            return None
        return self._hypothesis.formulate(gap, evidence, suspected_cause)

    # -- STEP 8 + 5: experiment + evaluate (controlled, no prod mutation) --
    def experiment(self, hyp: EvolutionHypothesis, baseline: float
                   ) -> "tuple[Experiment, EvaluationResult]":
        exp = Experiment(
            id="exp-stub", hypothesis_id=hyp.id,
            baseline=baseline, candidate=baseline, metric=hyp.metric,
            threshold=hyp.acceptance_threshold)
        ev = EvaluationResult(
            success=False, score_before=baseline, score_after=baseline,
            delta=0.0, regression=False,
            confidence=ConfidenceScore(0.0, ProvenanceType.RULE_INFERENCE),
            evidence="no experiment engine wired")
        if self._experiment is not None and self._evaluator is not None:
            exp = self._experiment.run(hyp, baseline)
            ev = self._evaluator.evaluate(baseline, exp.candidate, hyp.metric,
                                          hyp.acceptance_threshold)
        return exp, ev

    # -- STEP 9/10: accept / reject / rollback (delegate to existing writers)
    def decide(self, hyp: EvolutionHypothesis, exp: Experiment,
               ev: EvaluationResult) -> str:
        """Return ACCEPT / REJECT. Promotion/rollback is delegated to SkillEvolver."""
        if ev.success and exp.promoted:
            return "ACCEPT"
        return "REJECT"
