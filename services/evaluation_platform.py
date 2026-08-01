"""Evaluation Platform service (Wave 7, ADR-010 §4 / Roadmap Phase B+D).

BenchmarkRunner + MetricsCollector + InMemoryScorecard.

Dependency rule (LAW 2): this module imports ONLY `contracts`. It never imports
adapters or routers. The router is injected as a callable
`Callable[[ModelQuery], LlmResponse]` — a structural port, not the concrete
Router class (so services stay free of adapter imports).
"""
from __future__ import annotations

import statistics
from typing import Callable, Dict, List, Optional

from contracts.i_eval import (
    IBenchmark,
    IEvaluator,
    IScorecard,
    Scorecard,
    Task,
    TaskCategory,
)
from contracts.i_llm import LlmResponse, ModelQuery


# --------------------------------------------------------------------------
# MetricsCollector — IEvaluator (Phase D: 6 metrics)
# --------------------------------------------------------------------------
class MetricsCollector(IEvaluator):
    """Compute the six Wave 7 metrics for a (task, response) pair.

    accuracy         — exact / substring / rubric-hint match vs task.expected
    latency          — ms from LlmResponse.latency_ms
    cost             — from LlmResponse.cost
    stability        — placeholder (single run -> 1.0; multi-run fills variance)
    success_rate     — 1.0 if response.ok() else 0.0
    explainability   — 1.0 if decision_trace present else 0.5 (v0.1 heuristic)
    """

    # metric names (ADR-010 §4.1)
    ACCURACY = "accuracy"
    LATENCY = "latency_ms"
    COST = "cost"
    STABILITY = "stability"
    SUCCESS = "success_rate"
    EXPLAIN = "explainability_score"

    def evaluate(self, task: Task, response: LlmResponse) -> Dict[str, float]:
        out = (response.text or "").strip()
        metrics: Dict[str, float] = {}

        # accuracy
        acc = 0.0
        if task.expected:
            exp = task.expected.strip().lower()
            ol = out.lower()
            if ol == exp:
                acc = 1.0
            elif exp and exp in ol:
                acc = 0.7
        metrics[self.ACCURACY] = acc

        # latency / cost from the response (observability fields)
        metrics[self.LATENCY] = float(response.latency_ms or 0.0)
        metrics[self.COST] = float(response.cost or 0.0)

        # stability: single sample is perfectly stable by definition
        metrics[self.STABILITY] = 1.0

        # success
        metrics[self.SUCCESS] = 1.0 if response.ok() else 0.0

        # explainability: rewarded if the caller attached a decision trace
        metrics[self.EXPLAIN] = 1.0 if response.trace_id else 0.5
        return metrics


# --------------------------------------------------------------------------
# InMemoryScorecard — IScorecard storage (explicit state, LAW 3: no globals)
# --------------------------------------------------------------------------
class InMemoryScorecard(IScorecard):
    """In-process scorecard store (v0.1). v1.0 may back it with json/IFileSystem."""

    def __init__(self) -> None:
        # key (task_id, model_id) -> Scorecard
        self._store: Dict[tuple, Scorecard] = {}

    def record(self, scorecard: Scorecard) -> None:
        self._store[(scorecard.task_id, scorecard.model_id)] = scorecard

    def fetch(self, task_id: str, model_id: str) -> Optional[Scorecard]:
        return self._store.get((task_id, model_id))

    def leaderboard(self, model_id: str) -> float:
        accs = [
            sc.metrics.get(MetricsCollector.ACCURACY, 0.0)
            for (_, mid), sc in self._store.items()
            if mid == model_id
        ]
        if not accs:
            return 0.0
        return statistics.fmean(accs)


# --------------------------------------------------------------------------
# BenchmarkRunner — IBenchmark
# --------------------------------------------------------------------------
class BenchmarkRunner(IBenchmark):
    """Runs a task through a router (callable) and records a Scorecard.

    Does NOT make routing decisions (Roadmap: "НЕ принимает решения").
    It observes the decision the Router already made and measures it.
    """

    def __init__(
        self,
        evaluator: IEvaluator,
        scorecard: IScorecard,
    ) -> None:
        self._evaluator = evaluator
        self._scorecard = scorecard

    def run(
        self,
        task: Task,
        router: Callable[[ModelQuery], LlmResponse],
    ) -> Scorecard:
        query = ModelQuery(prompt=task.input, reasoning=(task.category == TaskCategory.REASONING))
        response = router(query)
        metrics = self._evaluator.evaluate(task, response)
        model_id = response.actual_model or response.model or "unknown"
        sc = Scorecard(
            task_id=task.id,
            model_id=model_id,
            output=response.text or "",
            metrics=metrics,
            evidence=(
                f"category={task.category}; "
                f"accuracy={metrics[MetricsCollector.ACCURACY]:.2f}; "
                f"latency={metrics[MetricsCollector.LATENCY]:.0f}ms; "
                f"cost={metrics[MetricsCollector.COST]:.4f}; "
                f"success={metrics[MetricsCollector.SUCCESS]:.0f}"
            ),
            decision_trace=response.trace_id or None,
        )
        self._scorecard.record(sc)
        return sc
