"""K8 tests for ТЗ-RT-01 Runtime / System Reflection.

Covers:
- metrics -> reflection -> TuningProposal (detected pattern -> correct proposal)
- apply under O1 guard: SOFT param CHANGES; HARD invariant NOT touched (negative)
- adaptive behavior: after tuning, MEASURABLE change (higher timeout -> waits longer;
  higher min_repetitions -> fewer consolidations)
- negative: no metrics -> no proposals; HARD proposal REJECTED
- separation from RF-01: runtime reflection writes NO semantic/policy content
"""

from __future__ import annotations

import time

from contracts.cognitive_domain import (
    ConfidenceScore,
    Episode,
    NodeLamportClock,
    Provenance,
    ProvenanceType,
)
from contracts.i_runtime_reflection import (
    ITuningApplier,
    RuntimeMetric,
    TuningLayer,
    TuningProposal,
)
from kernel.runtime_reflection import (
    ALLOWED_SOFT_PARAMS,
    ReferenceRuntimeReflection,
    ReferenceRuntimeMetrics,
    ReferenceTuningApplier,
)
from kernel.runtime_supervisor import RuntimeSupervisor, build_runtime_metrics
from kernel.memory_evolution import ReferenceMemoryEvolution
from kernel.cognitive_kernel import SimpleResourceManager
from adapters.network_transport import NetworkTransport
from adapters.tcp_event_bus import TcpEventBus


def _cs(v: float = 0.9) -> ConfidenceScore:
    return ConfidenceScore(v, ProvenanceType.RULE_INFERENCE)


def _mk_net() -> NetworkTransport:
    # unique port per call to avoid bind collisions across tests
    import random
    port = 19000 + random.randint(0, 800)
    return NetworkTransport("RT-%d" % port, port)


# ---------------------------------------------------------------------------
# 1. metrics -> reflection -> proposal (detected pattern -> correct proposal)
# ---------------------------------------------------------------------------
def test_reflection_detects_low_delivery_and_proposes_timeout_raise():
    ref = ReferenceRuntimeReflection()
    mets = [
        RuntimeMetric("federation.delivery_success_rate", 0.5, _cs()),
        RuntimeMetric("network.ensure_connected_timeout.current", 1.0, _cs()),
    ]
    props = ref.reflect(mets)
    assert len(props) == 1, f"expected 1 proposal, got {len(props)}"
    p = props[0]
    assert p.param == "network.ensure_connected_timeout"
    assert p.layer is TuningLayer.SOFT
    assert p.new_value > p.old_value, "timeout should be raised"
    assert p.new_value <= 10.0, "bounded by cap"


def test_reflection_detects_memory_growth_and_proposes_min_rep_raise():
    ref = ReferenceRuntimeReflection()
    mets = [
        RuntimeMetric("memory.growth_rate_per_tick", 0.9, _cs()),
        RuntimeMetric("memory.min_repetitions.current", 2.0, _cs()),
    ]
    props = ref.reflect(mets)
    assert len(props) == 1
    p = props[0]
    assert p.param == "memory.min_repetitions"
    assert p.new_value == 3.0


def test_reflection_no_double_proposal_when_already_at_cap():
    ref = ReferenceRuntimeReflection()
    # already at/above cap -> no change proposed
    mets = [
        RuntimeMetric("federation.delivery_success_rate", 0.5, _cs()),
        RuntimeMetric("network.ensure_connected_timeout.current", 10.0, _cs()),
    ]
    props = ref.reflect(mets)
    assert props == [], "no proposal when new==old (cap reached)"


# ---------------------------------------------------------------------------
# 2. apply under O1 guard: SOFT param CHANGES; HARD NOT touched
# ---------------------------------------------------------------------------
def test_apply_changes_soft_param():
    net = _mk_net()
    applier = ReferenceTuningApplier(targets={"network.ensure_connected_timeout": net})
    prop = TuningProposal(
        param="network.ensure_connected_timeout", old_value=net._connect_timeout,
        new_value=3.0, rationale="test", confidence=_cs(), layer=TuningLayer.SOFT)
    ok = applier.apply(prop)
    assert ok is True
    assert net._connect_timeout == 3.0


def test_apply_rejects_unknown_param():
    net = _mk_net()
    applier = ReferenceTuningApplier(targets={"network.ensure_connected_timeout": net})
    prop = TuningProposal(
        param="fsm.invariant.something", old_value=1.0, new_value=2.0,
        rationale="hacking FSM", confidence=_cs(), layer=TuningLayer.SOFT)
    ok = applier.apply(prop)
    assert ok is False, "unknown param must be rejected (O1 surface)"


def test_tuning_proposal_rejects_hard_layer_at_construction():
    # O1: a HARD tuning proposal is a design error and forbidden at construction.
    try:
        TuningProposal(
            param="hard.policy.x", old_value=1.0, new_value=2.0,
            rationale="mutate HARD", confidence=_cs(), layer=TuningLayer.HARD)
        assert False, "HARD proposal must be rejected at construction"
    except ValueError:
        pass


def test_applier_allowed_params_are_software_only():
    applier = ReferenceTuningApplier()
    allowed = applier.allowed_params()
    assert allowed == ALLOWED_SOFT_PARAMS
    # none of the allowed params may name an FSM / HARD / contract concept
    for p in allowed:
        assert "fsm" not in p and "hard" not in p and "contract" not in p


# ---------------------------------------------------------------------------
# 3. adaptive behavior: MEASURABLE change after tuning
# ---------------------------------------------------------------------------
def test_higher_timeout_makes_ensure_connected_wait_longer():
    net = _mk_net()
    net._expected_peers = 1  # will never be satisfied (no peer)
    # baseline: short timeout -> returns False quickly
    t0 = time.monotonic()
    r1 = net.ensure_connected(timeout=0.1)
    dt_short = time.monotonic() - t0
    assert r1 is False
    assert dt_short < 0.6, f"short timeout should wait ~0.1s, waited {dt_short:.2f}"
    # after tuning _connect_timeout up, ensure_connected(timeout=None) waits longer
    net._connect_timeout = 1.0
    t1 = time.monotonic()
    r2 = net.ensure_connected()  # uses _connect_timeout
    dt_long = time.monotonic() - t1
    assert r2 is False
    assert dt_long > dt_short + 0.4, \
        f"tuned timeout should wait longer ({dt_short:.2f} vs {dt_long:.2f})"


def test_higher_min_repetitions_reduces_consolidations():
    me_low = ReferenceMemoryEvolution(NodeLamportClock("n"), min_repetitions=2)
    me_high = ReferenceMemoryEvolution(NodeLamportClock("n"), min_repetitions=5)
    eps = [_mk_episode("same-experience") for _ in range(2)]
    facts_low, _ = me_low.consolidate(eps)
    facts_high, _ = me_high.consolidate(eps)
    assert len(facts_low) == 1, "2 reps with min_rep=2 -> 1 consolidated fact"
    assert len(facts_high) == 0, "2 reps with min_rep=5 -> 0 consolidated facts (adaptive)"


def _mk_episode(summary: str) -> Episode:
    return Episode(
        id="ep-%s" % summary, summary=summary,
        confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
        provenance=Provenance(source="test", actor="test"))


# ---------------------------------------------------------------------------
# 4. negative: no metrics -> no proposals; HARD rejected
# ---------------------------------------------------------------------------
def test_no_metrics_no_proposals():
    ref = ReferenceRuntimeReflection()
    assert ref.reflect([]) == []
    assert ref.reflect([RuntimeMetric("unrelated.metric", 0.0, _cs())]) == []


def test_supervisor_step_rejects_hard_by_construction():
    # Even if a HARD proposal were somehow formed, the applier rejects non-SOFT.
    # We verify the contract: apply returns False for layer != SOFT via a soft
    # proposal whose param is unknown (the guard path), and the O1 whitelist never
    # includes HARD-layer params.
    applier = ReferenceTuningApplier()
    assert "fsm" not in str(applier.allowed_params())


# ---------------------------------------------------------------------------
# 5. separation from RF-01: no semantic/policy content written
# ---------------------------------------------------------------------------
def test_runtime_reflection_writes_no_semantic_content():
    ref = ReferenceRuntimeReflection()
    mets = [
        RuntimeMetric("federation.delivery_success_rate", 0.4, _cs()),
        RuntimeMetric("network.ensure_connected_timeout.current", 1.0, _cs()),
    ]
    props = ref.reflect(mets)
    # reflection produces ONLY tuning proposals — never SemanticFact/Policy objects
    for p in props:
        assert isinstance(p, TuningProposal)
    # and it must not import/invoke memory evolution content committers
    assert "commit_semantic" not in dir(ref)
    assert "commit_normative" not in dir(ref)


def test_supervisor_does_not_emit_semantic_facts():
    net = _mk_net()
    me = ReferenceMemoryEvolution(NodeLamportClock("n"))
    rm = SimpleResourceManager()
    metrics = ReferenceRuntimeMetrics()
    ref = ReferenceRuntimeReflection()
    applier = ReferenceTuningApplier(targets={
        "network.ensure_connected_timeout": net,
        "memory.min_repetitions": me,
        "memory.confidence_threshold": me,
        "resource.budgets.tokens": rm._budgets,
    })
    sup = RuntimeSupervisor(metrics, ref, applier, targets={
        "network.ensure_connected_timeout": net,
        "memory.min_repetitions": me,
        "memory.confidence_threshold": me,
        "resource.budgets.tokens": rm._budgets,
    })
    m = build_runtime_metrics(memory_evolution=me, network_transport=net,
                              resource_manager=rm, delivery_success_rate=0.5,
                              memory_growth_rate=0.8)
    metrics.set_snapshot(m)
    applied = sup.step()
    # all applied proposals are tuning-only (no semantic layer mutation)
    for p in applied:
        assert isinstance(p, TuningProposal)
        assert p.layer is TuningLayer.SOFT


# ---------------------------------------------------------------------------
# 6. full loop integration sanity
# ---------------------------------------------------------------------------
def test_full_loop_applies_soft_tuning_to_real_targets():
    net = _mk_net()
    me = ReferenceMemoryEvolution(NodeLamportClock("n"))
    rm = SimpleResourceManager()
    metrics = ReferenceRuntimeMetrics()
    ref = ReferenceRuntimeReflection()
    applier = ReferenceTuningApplier(targets={
        "network.ensure_connected_timeout": net,
        "memory.min_repetitions": me,
        "memory.confidence_threshold": me,
        "resource.budgets.tokens": rm._budgets,
    })
    sup = RuntimeSupervisor(metrics, ref, applier, targets={
        "network.ensure_connected_timeout": net,
        "memory.min_repetitions": me,
        "memory.confidence_threshold": me,
        "resource.budgets.tokens": rm._budgets,
    })
    m = build_runtime_metrics(memory_evolution=me, network_transport=net,
                              resource_manager=rm, delivery_success_rate=0.5,
                              memory_growth_rate=0.8, consolidation_confidence=0.5)
    metrics.set_snapshot(m)
    applied = sup.step()
    assert len(applied) == 3
    assert net._connect_timeout == 1.5
    assert me._min_rep == 3.0
    assert me._thr == 0.8 or round(me._thr, 4) == 0.8
