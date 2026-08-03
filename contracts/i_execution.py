"""Execution layer contracts (ТЗ-EX-01, ADR-063).

K1-compliant: stdlib + contracts only. LLM-FREE core (reference environment).

Closes RF-01 ФЛАГ 2 (outcome-proxy): the system EXECUTES the chosen plan/action in an
environment and reads the REAL result instead of a proxy (`success = decision accepted`,
`utility = decision confidence`, which is almost always true).

Separation of concerns (critical, do NOT conflate):
- `ExecutionResult` = RAW answer from the environment (did the action succeed? what
  observation/reward came back?). Produced by IExecutor/IExecutionEnvironment.
- `ExecutionOutcome` (already in cognitive_domain, RF-01) = the feedback signal WRITTEN
  to Reflection. It is CONSTRUCTED FROM an ExecutionResult (success from result.success,
  utility from result.reward). Reflection never sees the raw environment; it sees Outcome.

O1: Execute does NOT mutate HARD layer / FSM invariants / contracts / kernel structure.
It only routes an Action to an executor and records the resulting Outcome.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from contracts.cognitive_domain import (
    Action,
    CausalMark,
    ConfidenceScore,
    Provenance,
    ProvenanceType,
)


@dataclass(frozen=True)
class ExecutionResult:
    """RAW result returned by the execution environment for one Action.

    This is NOT the Reflection feedback signal — `ExecutionOutcome` (cognitive_domain)
    is built FROM this (success <- result.success, utility <- result.reward).
    """
    action_id: str
    success: bool
    observation: str
    reward: float
    confidence: ConfidenceScore
    causal: CausalMark = field(default_factory=lambda: CausalMark("exec", 0))
    provenance: Provenance = field(
        default_factory=lambda: Provenance(source="execution", actor="executor"))


class IExecutionEnvironment(ABC):
    """The environment the action is stepped into. LLM-free reference is rule-based."""

    @abstractmethod
    def step(self, action: Action) -> ExecutionResult:
        """Apply `action` to the environment, return the raw ExecutionResult."""
        ...


class IExecutor(ABC):
    """Routes an Action to an execution environment and returns the raw result."""

    @abstractmethod
    def execute(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        """Execute `action` (optionally bounded by `timeout`) -> raw ExecutionResult."""
        ...


class IActionAdapter(ABC):
    """Optional adapter that maps an Action `kind` to a concrete environment call.

    Allows multiple environment backends (reference sim, real LLM/agent adapter) to be
    plugged in without changing the kernel Execute-phase (ADR-028 Kernel Purity).
    """
    # which action.kind this adapter handles
    kind: str = ""

    @abstractmethod
    def run(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        """Run the action in the backend this adapter wraps."""
        ...
