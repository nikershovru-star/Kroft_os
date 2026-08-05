"""Wave 7 (ADR-010) — service tests for Evaluation Platform.

BenchmarkRunner + MetricsCollector + InMemoryScorecard. Offline (fake router).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_eval import Task, TaskCategory, Scorecard
from contracts.i_llm import LlmResponse, ModelQuery
from services.evaluation_platform import (
    MetricsCollector,
    BenchmarkRunner,
    InMemoryScorecard,
)
from services.golden_dataset import fetch_dataset, fetch_by_category


def _resp(text, ok=True, **kw):
    # Build a real LlmResponse. ok() derives from error being None, so for a
    # failing response pass error="..." instead of ok=False.
    if not ok:
        kw["error"] = kw.get("error", "forced-failure")
    return LlmResponse(text=text, **kw)


def test_metrics_accuracy_exact():
    ev = MetricsCollector()
    t = Task(id="qa", category=TaskCategory.QA, input="q", expected="Paris")
    m = ev.evaluate(t, _resp("Paris"))
    assert m[MetricsCollector.ACCURACY] == 1.0


def test_metrics_accuracy_substring():
    ev = MetricsCollector()
    t = Task(id="qa", category=TaskCategory.QA, input="q", expected="Paris")
    m = ev.evaluate(t, _resp("The city is Paris, France"))
    assert m[MetricsCollector.ACCURACY] == 0.7


def test_metrics_accuracy_zero():
    ev = MetricsCollector()
    t = Task(id="qa", category=TaskCategory.QA, input="q", expected="Paris")
    m = ev.evaluate(t, _resp("London"))
    assert m[MetricsCollector.ACCURACY] == 0.0


def test_metrics_latency_cost_success_explain():
    ev = MetricsCollector()
    t = Task(id="r", category=TaskCategory.REASONING, input="q", expected="Yes")
    r = LlmResponse(text="Yes", latency_ms=320.0, cost=0.0, trace_id="t-1")
    m = ev.evaluate(t, r)
    assert m[MetricsCollector.LATENCY] == 320.0
    assert m[MetricsCollector.COST] == 0.0
    assert m[MetricsCollector.SUCCESS] == 1.0
    assert m[MetricsCollector.EXPLAIN] == 1.0
    assert m[MetricsCollector.STABILITY] == 1.0


def test_benchmarkrunner_records_scorecard():
    ev = MetricsCollector()
    store = InMemoryScorecard()
    runner = BenchmarkRunner(ev, store)
    t = Task(id="qa-001", category=TaskCategory.QA, input="capital of France?",
             expected="Paris")
    fake_router = lambda q: LlmResponse(text="Paris", actual_model="qwen",
                                        latency_ms=200.0, cost=0.0, trace_id="tr-9")
    sc = runner.run(t, fake_router)
    assert sc.model_id == "qwen"
    assert sc.metrics[MetricsCollector.ACCURACY] == 1.0
    assert store.fetch("qa-001", "qwen") is sc
    assert "accuracy" in sc.evidence


def test_scorecard_leaderboard_aggregates():
    store = InMemoryScorecard()
    store.record(Scorecard(task_id="a", model_id="m1", output="x",
                           metrics={MetricsCollector.ACCURACY: 1.0}))
    store.record(Scorecard(task_id="b", model_id="m1", output="x",
                           metrics={MetricsCollector.ACCURACY: 0.5}))
    assert store.leaderboard("m1") == 0.75
    assert store.leaderboard("unknown") == 0.0


def test_golden_dataset_has_five_categories():
    ds = fetch_dataset()
    cats = {t.category for t in ds}
    assert cats == set(TaskCategory.ALL)
    assert len(ds) >= 5


def test_golden_dataset_immutable_wrapped():
    # fetch_dataset returns a tuple (immutable container of frozen Tasks)
    ds = fetch_dataset()
    try:
        ds[0] = Task(id="x", category="qa", input="y")
        assert False, "dataset container must be immutable"
    except Exception:
        pass
