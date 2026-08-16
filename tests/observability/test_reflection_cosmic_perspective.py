"""ADR-028 Stage 3 — Cosmic perspective (Self-Observer scale awareness).

Proof-over-existence: a tiny task against a huge graph must report its TRUE
scale (e.g. 3 of 15000 -> ratio ~0.0002), never silently rounded to 0.
"""

from contracts.cognitive_domain import SelfObservationRecord
from kernel.reflection import ReferenceReflectionEngine
from contracts.cognitive_domain import NodeLamportClock


def test_small_task_reports_true_ratio_not_zero():
    eng = ReferenceReflectionEngine(NodeLamportClock("N"))
    rec = eng.observe_scale(
        total_nodes=15000,
        touched_node_ids=["n1", "n2", "n3"],
        activity_distribution={"retrieval": 72, "execution": 20, "self_improvement": 1},
        resolution_level="NODE",
    )
    assert isinstance(rec, SelfObservationRecord)
    assert rec.total_nodes == 15000
    assert rec.touched_nodes == 3
    # 3 / 15000 = 0.0002 -> NOT rounded to 0
    assert rec.touched_node_ratio == 0.0002, rec.touched_node_ratio
    assert rec.touched_node_ratio > 0.0


def test_activity_distribution_normalised_to_one():
    eng = ReferenceReflectionEngine(NodeLamportClock("N"))
    rec = eng.observe_scale(
        total_nodes=15000,
        touched_node_ids=["n1"],
        activity_distribution={"retrieval": 72, "execution": 20, "self_improvement": 1},
    )
    shares = dict(rec.activity_by_subsystem)
    total = sum(shares.values())
    assert abs(total - 1.0) < 1e-6, shares
    # self-improvement is practically inactive (1/93 ~= 0.0108)
    assert shares["self_improvement"] < 0.05


def test_zero_total_nodes_is_safe():
    eng = ReferenceReflectionEngine(NodeLamportClock("N"))
    rec = eng.observe_scale(total_nodes=0, touched_node_ids=[])
    assert rec.touched_node_ratio == 0.0
    assert rec.total_nodes == 0


def test_deterministic_for_same_input():
    eng = ReferenceReflectionEngine(NodeLamportClock("N"))
    a = eng.observe_scale(15000, ["n1", "n2"], {"retrieval": 3, "execution": 1}, "NODE")
    b = eng.observe_scale(15000, ["n1", "n2"], {"retrieval": 3, "execution": 1}, "NODE")
    assert a == b  # I-09
