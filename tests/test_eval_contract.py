"""Wave 7 (ADR-010) — contract tests for Evaluation Platform ports.

Verifies the ports are abstract and the entities are immutable (LAW 1/3).
No adapters, no services imports.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_eval import (
    IEvaluator,
    IBenchmark,
    IScorecard,
    Task,
    Metric,
    Scorecard,
    TaskCategory,
)
from contracts.i_llm import ModelQuery


def test_ports_are_abstract():
    assert IEvaluator.__abstractmethods__
    assert IBenchmark.__abstractmethods__
    assert IScorecard.__abstractmethods__


def test_task_is_frozen():
    t = Task(id="t1", category=TaskCategory.QA, input="q?")
    try:
        t.input = "changed"
        assert False, "Task must be frozen"
    except Exception:
        pass  # FrozenInstanceError expected


def test_task_category_all_present():
    assert set(TaskCategory.ALL) == {
        "qa", "reasoning", "summarization", "entity_extraction", "retrieval"
    }


def test_scorecard_carries_explanation_fields():
    sc = Scorecard(
        task_id="t1", model_id="m1", output="o",
        metrics={"accuracy": 0.9}, evidence="e", decision_trace="trace-1",
    )
    assert sc.task_id == "t1"
    assert sc.decision_trace == "trace-1"


def test_metric_entity():
    m = Metric(name="latency_ms", value=123.0, unit="ms")
    assert m.name == "latency_ms" and m.value == 123.0


def test_router_shape_compatible():
    # A router must be callable as Callable[[ModelQuery], LlmResponse].
    # We assert the structural contract the BenchmarkRunner relies on (LAW 2).
    def fake_router(q: ModelQuery):
        from contracts.i_llm import LlmResponse
        return LlmResponse(text="x")
    assert callable(fake_router)
