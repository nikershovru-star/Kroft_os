"""services/test_simple_self_evaluator.py — metrics from real fields (Wave 14).

Verifies LAW 3/4: EvaluationReport fields computed STRICTLY from Wave 12 fields
(ExecutionTrace.final_status, not a non-existent StepTrace.status) and from
rec_statuses snapshot (not ConfigApplier.history).
"""
from __future__ import annotations

from contracts.i_learning import ExecutionTrace, Pattern
from services.simple_self_evaluator import SimpleSelfEvaluator


def _trace(tid, status):
    return ExecutionTrace(trace_id=tid, goal="g", workflow_id="w", final_status=status)


def test_plan_success_rate_from_final_status() -> None:
    ev = SimpleSelfEvaluator()
    traces = [_trace("a", "done"), _trace("b", "done"), _trace("c", "failed")]
    rep = ev.evaluate(traces, [], {})
    assert abs(rep.plan_success_rate - 2 / 3) < 1e-9


def test_pattern_drift_from_rec_statuses() -> None:
    ev = SimpleSelfEvaluator()
    traces = [_trace("a", "done")]
    # 2 applied, 1 rolled_back -> drift = 2/3
    rep = ev.evaluate(traces, [], {"r1": "applied", "r2": "applied", "r3": "rolled_back"})
    assert abs(rep.pattern_drift - 2 / 3) < 1e-9


def test_optimization_yield_from_shipped() -> None:
    ev = SimpleSelfEvaluator()
    traces = [_trace("a", "done")]
    # proposed r1->approved, r2->applied, r3->proposed -> yield = 2/3
    rep = ev.evaluate(traces, [], {"r1": "approved", "r2": "applied", "r3": "proposed"})
    assert abs(rep.optimization_yield - 2 / 3) < 1e-9


def test_attention_flags_rolled_back() -> None:
    ev = SimpleSelfEvaluator()
    traces = [_trace("a", "done")]
    rep = ev.evaluate(traces, [], {"r1": "rolled_back"})
    assert "r1" in rep.attention


def test_report_is_frozen_and_attributable() -> None:
    ev = SimpleSelfEvaluator()
    traces = [_trace("a", "done"), _trace("b", "failed")]
    rep = ev.evaluate(traces, [], {})
    assert rep.trace_ids == ("a", "b")
    try:
        rep.plan_success_rate = 0.0  # type: ignore[misc]
        raise AssertionError("report mutable")
    except (AttributeError, TypeError):
        pass
