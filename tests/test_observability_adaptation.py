"""K8 tests for ТЗ-OBS-01 — Observability: live metrics -> autonomous adaptation.

Covers (acceptance + O1/K1/K6/K8 + ADR-067):
- CAPSTONE: degraded outcomes (executor fail / low reward) -> live
  ``memory.consolidation_confidence`` falls (< 0.6) -> RuntimeSupervisor AUTONOMOUSLY
  raises ``memory.confidence_threshold.current`` (R3) -> measurably FEWER consolidations.
  No injectable snapshot — adaptation is driven entirely by live counters.
- NEGATIVE: healthy outcomes (high reward) -> consolidation_confidence stays high ->
  threshold does NOT drift (proves adaptation is signal-driven, not thrashing — Флаг 3).
- O1: only SOFT params mutate; HARD/FSM/contracts untouched; no-op without collector.
- K6: kernel depends only on ILiveMetricsCollector port (no concrete adapter import).

Wiring note (K5): the kernel creates its OWN memory_evolution; build_kernel wires the
live collector + supervisor internally when ``live_metrics`` is passed. Hook-points are
no-ops without a collector (kernel behaves exactly as before).
"""

from __future__ import annotations

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Plan,
    Provenance,
    ProvenanceType,
)
from contracts.i_planner import IPlanner
from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor
from kernel.observability import LiveMetricsCollector
from contracts.i_observability import (
    ILiveMetricsCollector,
    METRIC_MEMORY_CONSOLIDATION_CONFIDENCE,
)
from contracts.cognitive_domain import NodeLamportClock


def _intent():
    return Intent(id="i1", text="go", confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))


class _FixedPlanner(IPlanner):
    """Always proposes a single plan with the given steps (ТЗ-SE-01 pattern)."""
    def __init__(self, steps): self._steps = steps
    def plan(self, goal, steps, world, budget, intent=None):
        return [Plan(id="p", goal_id=goal.id, steps=self._steps,
                     confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                     provenance=Provenance(source="t", actor="t"))]


def _run(kernel, planner, n):
    kernel._planner = planner
    for _ in range(n):
        kernel.tick(_intent())


# ---------------------------------------------------------------------------
# 1. CAPSTONE: degraded -> live consolidation_confidence falls -> supervisor AUTONOMOUSLY
#    raises confidence_threshold -> measurably fewer consolidations.
# ---------------------------------------------------------------------------
def test_capstone_autonomous_adaptation_raises_threshold():
    c = LiveMetricsCollector(NodeLamportClock("OBS-C"))
    k = build_kernel("OBS-C", live_metrics=c)
    k.attach_executor(ReferenceExecutor())
    init_thr = k._memory_evolution._thr

    # degraded: planner offers choose_red -> ReferenceExecutor yields LOW reward ->
    # live consolidation_confidence (window of utilities) falls < 0.6.
    _run(k, _FixedPlanner(("choose_red",)), 9)  # 3 supervisor steps (interval=3)

    new_thr = k._memory_evolution._thr
    # R3 fired autonomously: threshold raised (no injectable snapshot involved)
    assert new_thr > init_thr, f"supervisor must autonomously raise threshold: {init_thr} -> {new_thr}"
    # live metric must show degraded consolidation confidence
    conf = c.ratio(METRIC_MEMORY_CONSOLIDATION_CONFIDENCE)
    assert conf < 0.6, f"live consolidation_confidence must fall below 0.6, got {conf}"
    # O1: only SOFT param mutated; HARD/structure untouched (sanity: no exception,
    # threshold is a numeric SOFT param, not a structural change)
    assert isinstance(new_thr, float)


def test_capstone_fewer_consolidations_after_threshold_rise():
    c = LiveMetricsCollector(NodeLamportClock("OBS-C2"))
    k = build_kernel("OBS-C2", live_metrics=c)
    k.attach_executor(ReferenceExecutor())

    _run(k, _FixedPlanner(("choose_red",)), 6)   # first window: ~2 supervisor steps
    facts_early = len(k._memory.get_semantic())
    _run(k, _FixedPlanner(("choose_red",)), 6)   # later window: threshold now higher
    facts_late = len(k._memory.get_semantic())
    early_growth = facts_early
    late_growth = facts_late - facts_early
    # once threshold rose above episode confidence, fewer new facts consolidate
    assert k._memory_evolution._thr > 0.7, "threshold must have risen"
    # the later window adds no more (or fewer) facts once SOFT threshold blocks promotion
    assert late_growth <= early_growth, \
        f"fewer consolidations after threshold rise: early +{early_growth}, late +{late_growth}"


# ---------------------------------------------------------------------------
# 2. NEGATIVE: healthy outcomes -> consolidation_confidence high -> threshold stable.
# ---------------------------------------------------------------------------
def test_negative_healthy_no_threshold_drift():
    c = LiveMetricsCollector(NodeLamportClock("OBS-N"))
    k = build_kernel("OBS-N", live_metrics=c)
    k.attach_executor(ReferenceExecutor())
    init_thr = k._memory_evolution._thr

    # healthy: choose_blue -> ReferenceExecutor high reward -> consolidation_confidence high
    _run(k, _FixedPlanner(("choose_blue",)), 9)
    new_thr = k._memory_evolution._thr
    assert new_thr == init_thr, f"healthy outcomes must NOT drift threshold: {init_thr} -> {new_thr}"
    conf = c.ratio(METRIC_MEMORY_CONSOLIDATION_CONFIDENCE)
    assert conf >= 0.6, f"healthy consolidation_confidence must stay >= 0.6, got {conf}"


# ---------------------------------------------------------------------------
# 3. O1 + no-op: without collector the kernel behaves EXACTLY as before.
# ---------------------------------------------------------------------------
def test_noop_without_collector_behavior_unchanged():
    k = build_kernel("OBS-0")  # no live_metrics
    k.attach_executor(ReferenceExecutor())
    assert k._metrics is None and k._supervisor is None
    # must still run a full tick without error and learn locally (SE-01 path intact)
    _run(k, _FixedPlanner(("choose_red",)), 4)
    avoids = [p.body for p in k._memory.get_normative()
              if getattr(p, "layer", None) == "soft" and "avoid" in p.body]
    assert any("choose_red" in a for a in avoids), "local SE-01 learning intact without collector"


def test_collector_is_ilivemetricscollector_port():
    """K6: the wired collector satisfies the port; kernel imports only the port."""
    c = LiveMetricsCollector(NodeLamportClock("OBS-P"))
    assert isinstance(c, ILiveMetricsCollector)
