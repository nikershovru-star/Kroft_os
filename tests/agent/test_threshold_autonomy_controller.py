"""services/test_threshold_autonomy_controller.py — trigger logic (Wave 14).

Verifies the rate-limited trigger (loop-autonomy guard) and explicit mutable state.
"""
from __future__ import annotations

import time

from contracts.i_learning import ExecutionTrace
from services.threshold_autonomy_controller import ThresholdAutonomyController


def _trace(tid):
    return ExecutionTrace(trace_id=tid, goal="g", workflow_id="w", final_status="done")


def test_trigger_on_trace_count() -> None:
    c = ThresholdAutonomyController(min_traces=3, min_interval_s=0)
    assert c.should_retrospect([_trace(f"t{i}") for i in range(3)], {}) is True


def test_no_trigger_below_threshold() -> None:
    c = ThresholdAutonomyController(min_traces=5, min_interval_s=0)
    assert c.should_retrospect([_trace("t1"), _trace("t2")], {}) is False


def test_rate_limit_blocks_immediate_repeat() -> None:
    c = ThresholdAutonomyController(min_traces=1, min_interval_s=3600)
    assert c.should_retrospect([_trace("t1")], {}) is True   # first pass
    # immediate second call blocked by interval guard
    assert c.should_retrospect([_trace("t2")], {}) is False


def test_explicit_state_introspectable() -> None:
    c = ThresholdAutonomyController(min_traces=1, min_interval_s=0)
    assert c.retrospect_count() == 0
    c.should_retrospect([_trace("t1")], {})
    assert c.retrospect_count() == 1
    assert c.last_retrospect_at() > 0
