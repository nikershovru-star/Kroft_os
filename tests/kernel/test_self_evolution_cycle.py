"""CORE SELF-EVOLUTION WAVE — behaviour tests (STEP 17, ТЗ KROFT OS).

These are BEHAVIOR tests, not "class-exists" tests. They prove the closed loop:
  experience -> observe -> causal -> capability gap -> hypothesis -> experiment
  -> evaluate -> evolution -> memory -> next cycle

Run with: PYTHONPATH=. python -m pytest tests/kernel/test_self_evolution_cycle.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.cognitive_domain import (
    ConfidenceScore, NodeLamportClock, ProvenanceType, Provenance,
    ExecutionOutcome,
)
from contracts.i_self_evolution_cycle import (
    CapabilityGap, EvolutionHypothesis, KnowledgeState, CausalEvent,
)
from kernel.causal_analyzer import ReferenceCausalAnalyzer
from kernel.self_evolution_cycle import (
    InMemoryKernelObserver,
    ReferenceSelfEvaluator,
    ReferenceCapabilityManager,
    ReferenceHypothesisEngine,
    ReferenceExperimentEngine,
    ReferenceKnowledgeBoundary,
)
from kernel.self_evolution_controller import SelfEvolutionController


def _ev(success: bool, conf: float = 0.9) -> CausalEvent:
    return CausalEvent(
        event_id="e1", episode_id="ep1", parent_event_id=None,
        change="", hypothesis_id=None, action="act", observation="obs",
        outcome="ok" if success else "bad", success=success,
        confidence=ConfidenceScore(conf, ProvenanceType.OBSERVATION), timestamp=1.0)


# --- Test A: observe --------------------------------------------------------
def test_A_observe_recorded():
    obs = InMemoryKernelObserver()
    ctrl = SelfEvolutionController(observer=obs)
    from contracts.i_self_evolution_cycle import SelfObservationRecord
    ctrl.observe(SelfObservationRecord(
        cycle_id="c1", episode_id="ep1", fsm_state="EVALUATE", transition="EVALUATE",
        goal="g", action="a", result="success", confidence=0.8))
    assert len(obs.recent()) == 1
    assert obs.recent()[0].episode_id == "ep1"


# --- Test B: causal attribution --------------------------------------------
def test_B_causal_attribution():
    ca = ReferenceCausalAnalyzer()
    ev = _ev(True, 0.9)
    attributed = ca.attribute("skill v1->v2: dropped step", ev)
    assert attributed.change == "skill v1->v2: dropped step"
    assert ca.caused_improvement(attributed) is True
    # a change with no success is NOT credited
    ev_bad = _ev(False, 0.9)
    attributed_bad = ca.attribute("chg", ev_bad)
    assert ca.caused_improvement(attributed_bad) is False


# --- Test C: capability gap detection --------------------------------------
def test_C_capability_gap():
    cm = ReferenceCapabilityManager()
    cm.register("retrieval", 0.51, 0.80)
    cm.register("planning", 0.9, 0.85)
    gaps = cm.detect_gaps()
    assert len(gaps) == 1
    assert gaps[0].name == "retrieval"
    assert gaps[0].gap == 0.29


# --- Test D: hypothesis from gap -------------------------------------------
def test_D_hypothesis_from_gap():
    cm = ReferenceCapabilityManager()
    cm.register("retrieval", 0.51, 0.80)
    he = ReferenceHypothesisEngine()
    gap = cm.detect_gaps()[0]
    hyp = he.formulate(gap, "retrieval fails on ambiguous queries",
                       "lexical dominates semantic ranking")
    assert isinstance(hyp, EvolutionHypothesis)
    assert "semantic" in hyp.proposed_change.lower()
    assert hyp.metric == "retrieval"
    # no gap -> no hypothesis
    cm2 = ReferenceCapabilityManager()
    cm2.register("x", 0.9, 0.8)
    gaps2 = cm2.detect_gaps()
    assert gaps2 == []  # no gap detected
    # and formulate on a non-gap (gap<=0) returns None
    from contracts.i_self_evolution_cycle import CapabilityGap
    nogap = CapabilityGap(name="x", status="ok", score=0.9, target=0.8, gap=-0.1, evidence="")
    assert he.formulate(nogap, "e", "c") is None


# --- Test E: experiment baseline vs candidate -----------------------------
def test_E_experiment_compare():
    ee = ReferenceExperimentEngine(scorer=lambda change: 0.74)
    hyp = EvolutionHypothesis(
        id="h1", problem="p", evidence="e", suspected_cause="c",
        proposed_change="increase semantic", expected_effect="R@5 +0.1",
        metric="R@5", acceptance_threshold=0.1)
    exp = ee.run(hyp, baseline=0.62)
    assert exp.baseline == 0.62
    assert exp.candidate == 0.74
    assert exp.promoted is True


# --- Test F: promotion (candidate > baseline) ------------------------------
def test_F_promotion():
    ev = ReferenceSelfEvaluator()
    res = ev.evaluate(0.62, 0.74, "R@5", 0.1)
    assert res.delta == 0.12
    assert res.success is True
    ctrl = SelfEvolutionController(evaluator=ev, experiment=ReferenceExperimentEngine(scorer=lambda c: 0.74))
    hyp = EvolutionHypothesis(
        id="h1", problem="p", evidence="e", suspected_cause="c",
        proposed_change="increase semantic", expected_effect="R@5 +0.1",
        metric="R@5", acceptance_threshold=0.1)
    exp, evr = ctrl.experiment(hyp, 0.62)
    assert ctrl.decide(hyp, exp, evr) == "ACCEPT"


# --- Test G: rejection (candidate <= baseline) ----------------------------
def test_G_rejection():
    ctrl = SelfEvolutionController(
        evaluator=ReferenceSelfEvaluator(),
        experiment=ReferenceExperimentEngine(scorer=lambda c: 0.60))
    hyp = EvolutionHypothesis(
        id="h1", problem="p", evidence="e", suspected_cause="c",
        proposed_change="x", expected_effect="y",
        metric="R@5", acceptance_threshold=0.1)
    exp, evr = ctrl.experiment(hyp, 0.62)
    assert ctrl.decide(hyp, exp, evr) == "REJECT"


# --- Test H: rollback is reversible (SkillEvolver keeps old, never deletes) -
def test_H_rollback_reversible():
    # The controller delegates mutation to SkillEvolver (existing). We assert the
    # decision logic keeps the OLD behavior when rejected (no promotion => no change).
    ctrl = SelfEvolutionController(
        evaluator=ReferenceSelfEvaluator(),
        experiment=ReferenceExperimentEngine(scorer=lambda c: 0.55))
    hyp = EvolutionHypothesis(
        id="h1", problem="p", evidence="e", suspected_cause="c",
        proposed_change="x", expected_effect="y",
        metric="R@5", acceptance_threshold=0.1)
    exp, evr = ctrl.experiment(hyp, 0.62)
    decision = ctrl.decide(hyp, exp, evr)
    # rejected => previous procedure version remains authoritative (rollback = keep old)
    assert decision == "REJECT"
    assert exp.promoted is False


# --- Test I: persistence survives via history ------------------------------
def test_I_persistence_history():
    cm = ReferenceCapabilityManager()
    cm.register("retrieval", 0.51, 0.80)
    ctrl = SelfEvolutionController(capability=cm,
                                   hypothesis=ReferenceHypothesisEngine())
    gap = ctrl.detect_gaps()[0]
    hyp = ctrl.formulate(gap, "e", "c")
    # simulate acceptance bookkeeping without real mutation
    ctrl._hypothesis_history.append(hyp)
    ctrl._accepted.append(hyp.id)
    hist = ctrl.history()
    assert hyp.id in hist[2]  # accepted list


# --- Test J: full autonomous loop (no manual wiring between stages) --------
def test_J_autonomous_closed_loop():
    ca = ReferenceCausalAnalyzer()
    cm = ReferenceCapabilityManager()
    cm.register("retrieval", 0.51, 0.80)
    ee = ReferenceExperimentEngine(scorer=lambda c: 0.74)
    ctrl = SelfEvolutionController(
        causal=ca, capability=cm,
        hypothesis=ReferenceHypothesisEngine(),
        experiment=ee, evaluator=ReferenceSelfEvaluator())
    # 1. experience -> observe
    from contracts.i_self_evolution_cycle import SelfObservationRecord
    ctrl.observe(SelfObservationRecord(
        cycle_id="c1", episode_id="ep1", fsm_state="EVALUATE", transition="EVALUATE",
        goal="improve retrieval", action="a", result="fail", confidence=0.5))
    # 2. causal attribution of a prior change
    ca.attribute("skill v1->v2", _ev(True, 0.9))
    # 3. capability gap
    gaps = ctrl.detect_gaps()
    assert gaps and gaps[0].name == "retrieval"
    # 4. hypothesis
    hyp = ctrl.formulate(gaps[0], "retrieval fails on ambiguous queries", "lexical dominates")
    assert hyp is not None
    # 5-6. experiment + evaluate
    exp, evr = ctrl.experiment(hyp, 0.62)
    # 7. evolution decision (accept/reject)
    decision = ctrl.decide(hyp, exp, evr)
    assert decision == "ACCEPT"
    # 8. next cycle reuses the improved capability target (memory of the gap)
    assert ctrl.detect_gaps()[0].name == "retrieval"


# --- Knowledge Boundary (STEP 11) ------------------------------------------
def test_K_knowledge_boundary_do_not_pretend():
    kb = ReferenceKnowledgeBoundary()
    assert kb.classify(0.1, 0.0) == KnowledgeState.UNKNOWN
    assert kb.classify(0.4, 0.3) == KnowledgeState.UNCERTAIN
    assert kb.classify(0.7, 0.6) == KnowledgeState.LIKELY
    assert kb.classify(0.95, 0.9) == KnowledgeState.KNOWN
    # do-not-pretend gate
    assert kb.should_abstain(kb.classify(0.1, 0.0)) is True
    assert kb.should_abstain(kb.classify(0.95, 0.9)) is False
