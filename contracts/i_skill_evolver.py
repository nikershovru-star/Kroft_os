"""Skill Evolver port — self-improving skills (ТЗ-EVOLUTION-01, ADR-092).

K1-compliant: stdlib + contracts only. K5: this is a NEW orchestration seam (usage-stats ->
propose improvement -> sandbox-test -> update skill). It does NOT duplicate existing ports:
  - contracts/i_execution_sandbox.py already has IExecutionSandbox (ADR-039) + ExecutionResult.
    We REUSE IExecutionSandbox for isolated variant testing (never reimplement a sandbox).
  - contracts/i_memory.py already has Procedure (frozen skill VO) + IProceduralMemory
    (store_skill / recall_skill_by_capability / record_skill_outcome). We REUSE Procedure,
    and extend it (version + lifecycle) for versioned supersession.
  - contracts/cognitive_domain.py already has PolicyLifecycle (ACTIVE/DEPRECATED/SUPERSEDED).
    We REUSE PolicyLifecycle.SUPERSEDED to mark replaced skills (traceability, no deletion).
The missing piece was the evolution orchestration boundary itself -> ISkillEvolver/ISkillEvaluator.

Determinism (I-09): the LLM-free heuristic propose/test path is deterministic so tests are stable.
O1: sandbox testing is isolated (subprocess) and time-bounded; a failing variant NEVER crashes the
kernel and NEVER mutates HARD/FSM — the old skill is kept unless the new one is strictly better.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

from contracts.cognitive_domain import PolicyLifecycle
from contracts.i_execution_sandbox import ExecutionResult
from contracts.i_memory import Procedure


@dataclass(frozen=True)
class SkillUsageStats:
    """Usage/efficiency stats for a skill (ТЗ-EVOLUTION-01, ТЗ-SKILL-EVOLVE-01).

    Reuses nothing new — plain aggregate the procedural memory already tracks.
    """

    capability: str
    uses: int
    success_rate: float


@dataclass(frozen=True)
class SkillVariant:
    """A proposed improvement of a skill (ТЗ-EVOLUTION-01).

    Frozen VO: which skill, the new steps, and the proposed version number.
    """

    skill_id: str
    capability: str
    new_steps: Tuple[str, ...]
    version: int


@dataclass(frozen=True)
class EvalResult:
    """Outcome of testing a SkillVariant in the sandbox (ТЗ-EVOLUTION-01).

    score is a deterministic 0..1 quality measure; better_than_baseline gates the update.
    """

    score: float
    better_than_baseline: bool
    detail: str = ""


class ISkillEvolver(ABC):
    """Port: propose a skill improvement from usage stats (ТЗ-EVOLUTION-01).

    Contract:
      - propose_improvement(skill, stats) returns a SkillVariant when the skill has enough
        usage AND low enough efficiency, else None (no change). LLM-free heuristic by default;
        an optional LLM advisor may enrich the proposal (non-blocking fallback).
      - MUST be deterministic on the LLM-free path (I-09).
    """

    @abstractmethod
    def propose_improvement(self, skill: Procedure,
                            stats: SkillUsageStats) -> "SkillVariant | None":
        raise NotImplementedError


class ISkillEvaluator(ABC):
    """Port: test a SkillVariant in an isolated sandbox (ТЗ-EVOLUTION-01).

    Contract:
      - test_in_sandbox(variant, baseline_score) runs variant.new_steps through an
        IExecutionSandbox and returns an EvalResult. Isolated (subprocess), time-bounded.
      - MUST NOT mutate the live skill store or HARD/FSM (O1).
      - On sandbox failure MUST return a low-score EvalResult, not raise.
    """

    @abstractmethod
    def test_in_sandbox(self, variant: SkillVariant,
                       baseline_score: float) -> EvalResult:
        raise NotImplementedError
