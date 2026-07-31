"""IPlanner / IExecutor / IReflection / IRetryManager — Workflow Platform ports
(Wave 10, ADR-013).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Definition of Done (Roadmap Wave 10):

    Any workflow can be saved, replayed and reproduced.

Which is why:
- `Workflow` and `Step` are frozen and carry ONLY scalar/JSON-native fields;
- there is NO timestamp anywhere in the entities — a clock reading would make
  two runs of the same input unequal and break reproducibility. Timing belongs
  to Evaluation (Wave 7) `Scorecard`, not to the workflow record;
- state transitions are copy-on-write (`with_*` helpers), never mutation.
"""
from __future__ import annotations

import abc
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from contracts.i_eval import Scorecard
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext

# Structural port for the router (LAW 2): services must not import adapters,
# so the executor receives a callable rather than the concrete Router class.
RouterFn = Callable[[ModelQuery], LlmResponse]


class StepStatus:
    """Lifecycle of a single step (immutable taxonomy)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    ALL = (PENDING, RUNNING, DONE, FAILED)


class WorkflowStatus:
    """Lifecycle of a workflow (immutable taxonomy)."""

    DRAFT = "draft"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    ALL = (DRAFT, RUNNING, DONE, FAILED)


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Step:
    """One unit of work. Immutable (LAW 3); transitions return new objects.

    Every field is JSON-native so the whole plan survives a round trip.
    `route_used` / `attempts` / `reflection_score` are the evidence trail
    required by LAW 4.
    """

    id: str
    task: str
    status: str = StepStatus.PENDING
    output: str = ""
    attempts: int = 0
    route_used: str = ""          # actual_model / provider that served the step
    reflection_score: float = 0.0
    error: str = ""

    def with_status(self, status: str) -> "Step":
        return replace(self, status=status)

    def with_result(
        self,
        output: str,
        route_used: str = "",
        reflection_score: float = 0.0,
        status: str = StepStatus.DONE,
        error: str = "",
    ) -> "Step":
        return replace(
            self,
            output=output,
            route_used=route_used,
            reflection_score=reflection_score,
            status=status,
            error=error,
        )

    def with_attempt(self) -> "Step":
        return replace(self, attempts=self.attempts + 1)

    @property
    def is_terminal(self) -> bool:
        return self.status in (StepStatus.DONE, StepStatus.FAILED)


@dataclass(frozen=True)
class Workflow:
    """A task as DATA, not as a call chain (ADR-013 §1).

    Frozen: the executor returns a NEW workflow rather than mutating the one it
    was given, so the caller keeps the original for comparison/replay.

    `variables` stays a plain dict on purpose (ADR-013 §2.2): the JSON shape
    `{"k": "v"}` is human-readable and hand-editable, which directly serves the
    "save and replay" DoD. It is defensively COPIED in __post_init__ so an
    outside mutation cannot leak in, and every update goes through
    `with_variables()`, which copies again.
    """

    id: str
    goal: str
    plan: Tuple[Step, ...] = ()
    variables: Dict[str, str] = field(default_factory=dict)
    status: str = WorkflowStatus.DRAFT
    reflection_log: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # normalise sequences to tuples (a frozen dataclass freezes the
        # reference, not the container — pitfall from Wave 8/9)
        object.__setattr__(self, "plan", tuple(self.plan or ()))
        object.__setattr__(self, "reflection_log", tuple(self.reflection_log or ()))
        # defensive copy: the caller's dict must not alias our state
        object.__setattr__(self, "variables", dict(self.variables or {}))

    # --- copy-on-write transitions ----------------------------------------
    def with_status(self, status: str) -> "Workflow":
        return replace(self, status=status)

    def with_plan(self, plan) -> "Workflow":
        return replace(self, plan=tuple(plan))

    def with_step(self, index: int, step: Step) -> "Workflow":
        """Return a NEW workflow with the step at `index` replaced."""
        plan = list(self.plan)
        plan[index] = step
        return replace(self, plan=tuple(plan))

    def with_variables(self, **updates: str) -> "Workflow":
        merged = dict(self.variables)
        merged.update(updates)
        return replace(self, variables=merged)

    def with_log(self, *lines: str) -> "Workflow":
        return replace(self, reflection_log=self.reflection_log + tuple(lines))

    # --- lookups -----------------------------------------------------------
    def step(self, step_id: str) -> Optional[Step]:
        return next((s for s in self.plan if s.id == step_id), None)

    @property
    def failed_steps(self) -> List[Step]:
        return [s for s in self.plan if s.status == StepStatus.FAILED]

    @property
    def is_complete(self) -> bool:
        return bool(self.plan) and all(s.status == StepStatus.DONE for s in self.plan)

    # --- persistence (the Wave 10 DoD) -------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """JSON-native dict. Tuples degrade to lists — that is fine and lossless."""
        return asdict(self)

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        payload = dict(data)
        payload["plan"] = tuple(Step(**s) for s in payload.get("plan", ()))
        return cls(**payload)

    @classmethod
    def from_json(cls, raw: str) -> "Workflow":
        return cls.from_dict(json.loads(raw))


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IPlanner(abc.ABC):
    """Turn a goal into an ordered list of steps.

    v0.1 is rule-based; an LLM planner arrives in Wave 11 as the second
    implementation of this same port.
    """

    @abc.abstractmethod
    def plan(self, goal: str, context: PolicyContext) -> List[Step]:
        """Decompose `goal` into steps. Must be deterministic for the DoD."""
        raise NotImplementedError


class IExecutor(abc.ABC):
    """Run a workflow's plan and return the completed workflow."""

    @abc.abstractmethod
    def execute(self, workflow: Workflow, router: RouterFn) -> Workflow:
        """Execute every step via `router`, returning a NEW workflow.

        `router` is a callable port, not the concrete adapters.Router — a
        service may not import an adapter (LAW 2).
        """
        raise NotImplementedError


class IReflection(abc.ABC):
    """Decide whether a step's output is acceptable."""

    @abc.abstractmethod
    def evaluate_step(self, step: Step, scorecard: Optional[Scorecard] = None) -> bool:
        """True when the output is good enough to move on."""
        raise NotImplementedError

    @abc.abstractmethod
    def score(self, step: Step, scorecard: Optional[Scorecard] = None) -> float:
        """Numeric quality score, always recorded even when it fails (LAW 5)."""
        raise NotImplementedError


class IRetryManager(abc.ABC):
    """Decide whether and HOW to retry a step.

    Retrying the identical query is pointless (ADR-013 §2.4): the manager
    rewrites the query/context so the PolicyEngine picks a different route.
    """

    @abc.abstractmethod
    def should_retry(self, step: Step) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def prepare_retry(
        self,
        query: ModelQuery,
        context: PolicyContext,
        attempt: int,
    ) -> Tuple[ModelQuery, PolicyContext]:
        """Return a MODIFIED (query, context) aimed at a different route."""
        raise NotImplementedError

    @abc.abstractmethod
    def explain(self, attempt: int) -> str:
        """Human-readable description of what the next attempt changes (LAW 4)."""
        raise NotImplementedError
