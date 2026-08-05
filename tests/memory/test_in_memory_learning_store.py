"""adapters/test_in_memory_learning_store.py — record/query/aggregate (Wave 12).

Verifies LAW 6: InMemoryLearningStore is a wrapper over IMemoryStore, not a new
storage engine. Also checks serialization round-trip of nested frozen dataclasses.
"""
from __future__ import annotations

import os

from adapters.in_memory_learning_store import InMemoryLearningStore
from contracts.i_learning import ExecutionTrace, StepTrace
from adapters.in_memory_memory_store import InMemoryMemoryStore
from contracts.i_memory import MemoryKind

os.environ.setdefault("LEARNING_LIVE", "0")  # no network needed here


def _make_store():
    return InMemoryLearningStore(InMemoryMemoryStore())


def _trace(tid, goal, model, eval_score, status="done"):
    return ExecutionTrace(
        trace_id=tid,
        goal=goal,
        workflow_id="w-" + tid,
        steps=(StepTrace(step_id="s1", model_id=model, prompt=goal, output="o", eval_score=eval_score),),
        final_status=status,
        timestamp=1.0,
        tags=(status,),
    )


def test_record_then_query_by_tag() -> None:
    store = _make_store()
    store.record(_trace("t1", "reasoning task", "phi4", 0.91))
    found = store.query("reasoning")
    assert len(found) == 1
    assert found[0].trace_id == "t1"
    assert found[0].steps[0].model_id == "phi4"
    assert found[0].steps[0].eval_score == 0.91


def test_query_uses_memory_tag() -> None:
    store = _make_store()
    store.record(_trace("t2", "code generation", "gpt", 0.85))
    # underlying store should carry the LEARNING tag, not pollute other tags
    from contracts.i_memory import MemoryQuery

    raw = store._store.query(MemoryQuery())
    assert all(MemoryKind.LEARNING in (i.tags or ()) for i in raw)


def test_aggregate_avg_eval_score_by_model() -> None:
    store = _make_store()
    store.record(_trace("a", "reasoning task", "phi4", 0.90))
    store.record(_trace("b", "reasoning task", "phi4", 0.92))
    store.record(_trace("c", "reasoning task", "gpt", 0.80))
    res = store.aggregate("avg_eval_score", "model_id")
    assert res["phi4"] == 0.91
    assert res["gpt"] == 0.80


def test_aggregate_avg_latency_by_model() -> None:
    store = _make_store()
    t = ExecutionTrace(
        trace_id="l1", goal="g", workflow_id="w", steps=(
            StepTrace(step_id="s1", model_id="phi4", prompt="p", output="o", latency_ms=100.0),
            StepTrace(step_id="s2", model_id="phi4", prompt="p", output="o", latency_ms=200.0),
        ),
        final_status="done", timestamp=1.0,
    )
    store.record(t)
    assert store.aggregate("avg_latency", "model_id")["phi4"] == 150.0


def test_aggregate_success_rate() -> None:
    store = _make_store()
    store.record(_trace("ok1", "reasoning task", "phi4", 0.9, "done"))
    store.record(_trace("ok2", "reasoning task", "phi4", 0.9, "done"))
    store.record(_trace("fail", "reasoning task", "phi4", 0.9, "failed"))
    # success_rate = per-step done ratio across all traces' steps (2 done + 1 failed)
    res = store.aggregate("success_rate", "model_id")
    assert abs(res["phi4"] - (2.0 / 3.0)) < 1e-9


def test_aggregate_rejects_unknown_metric() -> None:
    store = _make_store()
    store.record(_trace("x", "g", "m", 0.5))
    try:
        store.aggregate("bogus", "model_id")
        raise AssertionError("unknown metric accepted")
    except ValueError:
        pass


def test_serialization_roundtrip_nested() -> None:
    store = _make_store()
    t = _trace("rt", "reasoning task", "phi4", 0.88)
    store.record(t)
    got = store.query("reasoning")[0]
    assert isinstance(got.steps[0], StepTrace)
    assert got.steps[0].eval_score == 0.88
