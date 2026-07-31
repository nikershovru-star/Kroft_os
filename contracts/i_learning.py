"""(contracts) ILearningStore / IPatternExtractor — Learning Platform ports
(Wave 12, ADR-015).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Definition of Done (Roadmap Wave 12):

    The system can analyse its own history.

Every AgentPlatform.run() yields an immutable `ExecutionTrace`. The trace is
stored and queryable through a specialised port (ILearningStore) whose semantics
differ from generic memory: grouping, aggregation, trends. ILearningStore is a
*semantic* port over IMemoryStore (Wave 9) — it does NOT own storage (LAW 6).

`ExecutionTrace` / `StepTrace` are frozen like `Fact` (Wave 8) and `AgentResult`
(Wave 11): a run is data, not a side effect. No update() methods — an error in a
trace is a NEW trace flagged `corrected=True` (carried in `tags`).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StepTrace:
    """One executed step, recorded for later analysis (ADR-015 §2).

    `model_id` is the ACTUAL model/route that served the step (from
    `Step.route_used`). `eval_score` comes from Wave 7's Evaluation Platform,
    surfaced here via `Step.reflection_score`.
    """

    step_id: str
    model_id: str
    prompt: str
    output: str
    tools_used: Tuple[str, ...] = ()
    cost: float = 0.0
    latency_ms: float = 0.0
    eval_score: float = 0.0  # from Evaluation Platform (Wave 7)


@dataclass(frozen=True)
class ExecutionTrace:
    """Immutable record of one agent run (ADR-015 §2).

    Append-only. Built by AgentPlatform after a run completes. `timestamp` is a
    wall-clock reading — acceptable here because a *trace* is an audit artifact,
    not a reproducibility key (unlike Workflow, which forbids clocks).
    """

    trace_id: str
    goal: str
    workflow_id: str
    steps: Tuple[StepTrace, ...] = ()
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    final_status: str = ""  # done | failed
    timestamp: float = 0.0
    tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Pattern:
    """A learning extracted from history (ADR-015 §2, LAW 4).

    Carries the evidence discipline required by LAW 4: `confidence` + `applies_to`
    so a recommendation is attributable and scoping, never a vague guess.
    """

    description: str
    confidence: float  # 0.0–1.0
    applies_to: Tuple[str, ...]  # e.g. ("reasoning", "local")
    recommendation: str  # human-readable, e.g. "Use phi4 for reasoning tasks"


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class ILearningStore(abc.ABC):
    """Analysis semantics over stored execution traces (LAW 6: wraps IMemoryStore)."""

    @abc.abstractmethod
    def record(self, trace: ExecutionTrace) -> None:
        """Persist an immutable trace (append-only)."""
        raise NotImplementedError

    @abc.abstractmethod
    def query(self, pattern: str, limit: int = 10) -> List[ExecutionTrace]:
        """Return recent traces whose goal/content matches `pattern` (substring)."""
        raise NotImplementedError

    @abc.abstractmethod
    def aggregate(self, metric: str, group_by: str) -> Dict[str, float]:
        """Aggregate a metric across traces, grouped.

        metric:    "avg_latency" | "avg_cost" | "success_rate" | "avg_eval_score"
        group_by:  "model_id" | "provider" | "task_type"
        Returns {group_key: float}. LAW 5: numbers, not guesses.
        """
        raise NotImplementedError


class IPatternExtractor(abc.ABC):
    """Turn accumulated traces into actionable patterns (ADR-015 §2)."""

    @abc.abstractmethod
    def extract(self, traces: List[ExecutionTrace]) -> List[Pattern]:
        """Aggregate traces and emit patterns (recommendations)."""
        raise NotImplementedError
