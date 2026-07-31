"""IEvaluator / IBenchmark / IScorecard — Evaluation Platform ports (Wave 7, ADR-010).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

The Evaluation Platform turns routing from heuristic into *measurable* decision
(LAW 4: Decision -> Evidence -> Explanation; LAW 5: no automation without measurement).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from contracts.i_llm import LlmResponse, ModelQuery


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
class TaskCategory:
    """Golden Dataset categories (immutable taxonomy, ADR-010 §4.1)."""
    QA = "qa"
    REASONING = "reasoning"
    SUMMARIZATION = "summarization"
    ENTITY_EXTRACTION = "entity_extraction"
    RETRIEVAL = "retrieval"

    ALL = (QA, REASONING, SUMMARIZATION, ENTITY_EXTRACTION, RETRIEVAL)


@dataclass(frozen=True)
class Task:
    """One immutable evaluation item. Golden Dataset is built from these."""
    id: str
    category: str
    input: str
    expected: Optional[str] = None       # ground truth for exact metrics
    rubric: Optional[str] = None          # free-text grading guide (v1.0 LLM-judge)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Metric:
    """A single measured quantity (ADR-010 §4.1)."""
    name: str
    value: float
    unit: str = ""


@dataclass
class Scorecard:
    """Result of evaluating one (task, model) pair (ADR-010 §4.1).

    Carries Decision -> Evidence -> Explanation (LAW 4): the model was chosen,
    the metrics are the evidence, the decision_trace is the explanation.
    """
    task_id: str
    model_id: str
    output: str
    metrics: Dict[str, float] = field(default_factory=dict)
    evidence: str = ""
    decision_trace: Optional[str] = None


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IEvaluator(abc.ABC):
    """Compute metrics for a (task, response) pair.

    Pure function: no I/O, no hidden state (LAW 3). Implementations may add
    latency/cost from the response and semantic metrics from task+output.
    """

    @abc.abstractmethod
    def evaluate(self, task: Task, response: LlmResponse) -> Dict[str, float]:
        """Return a metric-name -> value mapping."""
        raise NotImplementedError


class IBenchmark(abc.ABC):
    """Run a single task through a router and produce a Scorecard."""

    @abc.abstractmethod
    def run(
        self,
        task: Task,
        router: Callable[[ModelQuery], LlmResponse],
    ) -> Scorecard:
        """Execute task via `router` (callable port — not a concrete Router,
        to respect LAW 2: services must not import adapters)."""
        raise NotImplementedError


class IScorecard(abc.ABC):
    """Storage port for scorecards (explicit state object, LAW 3 — no globals)."""

    @abc.abstractmethod
    def record(self, scorecard: Scorecard) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def fetch(self, task_id: str, model_id: str) -> Optional[Scorecard]:
        raise NotImplementedError

    @abc.abstractmethod
    def leaderboard(self, model_id: str) -> float:
        """Aggregated accuracy for a model across recorded tasks (0.0 if none)."""
        raise NotImplementedError
