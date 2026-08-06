"""SkillEvolver — self-improving skills (ТЗ-EVOLUTION-01, ADR-092).

K6: lives in services/ — imports ONLY contracts (i_skill_evolver, i_memory, i_execution_sandbox,
cognitive_domain). The sandbox (IExecutionSandbox) + procedural memory (IProceduralMemory) are
INJECTED (never imported concrete), so this module stays axis-clean (services -> contracts only).

Closed loop (ТЗ-EVOLUTION-01): usage stats -> propose improvement -> sandbox-test -> update skill.
  - LLM-free heuristic propose (I-09 deterministic): when uses >= N and success_rate < threshold,
    drop the longest/least-reliable step (heuristic) to propose a shorter variant. Optional LLM
    advisor may enrich (non-blocking fallback to heuristic).
  - sandbox test: each variant step is run as an isolated subprocess command; score = fraction of
    steps that exit 0 (deterministic). O1: sandbox failures -> low score, never a crash, never
    mutate HARD/FSM.
  - update: if the variant scores strictly better than the baseline, store the new Procedure
    (version+1, ACTIVE) and mark the old one SUPERSEDED (kept in history for traceability).
    If not better, the old skill is preserved unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from dataclasses import replace

from contracts.cognitive_domain import PolicyLifecycle
from contracts.i_execution_sandbox import ExecutionResult, IExecutionSandbox
from contracts.i_memory import IProceduralMemory, Procedure
from contracts.i_skill_evolver import (
    EvalResult,
    ISkillEvaluator,
    ISkillEvolver,
    SkillUsageStats,
    SkillVariant,
)


class SkillEvolver(ISkillEvolver, ISkillEvaluator):
    """Reference Skill Evolver: propose + sandbox-test + versioned update (ТЗ-EVOLUTION-01)."""

    def __init__(self, sandbox: IExecutionSandbox, memory: IProceduralMemory,
                 min_uses: int = 5, success_threshold: float = 0.8,
                 timeout_sec: float = 5.0, advisor=None) -> None:
        # sandbox + memory INJECTED (composition supplies SubprocessSandbox / InMemoryProceduralMemory)
        self._sandbox = sandbox
        self._memory = memory
        self._min_uses = min_uses
        self._threshold = success_threshold
        self._timeout = timeout_sec
        self._advisor = advisor  # optional LLM advisor (non-blocking)
        # capability -> list of SUPERSEDED old Procedures (traceability)
        self._history: Dict[str, List[Procedure]] = {}

    # --- ISkillEvolver -------------------------------------------------------
    def propose_improvement(self, skill: Procedure,
                            stats: SkillUsageStats) -> Optional[SkillVariant]:
        if stats.uses < self._min_uses:
            return None
        if stats.success_rate >= self._threshold:
            return None
        # LLM-free heuristic: propose a shorter variant by dropping the longest step.
        steps = list(skill.steps)
        if len(steps) <= 1:
            return None
        longest_idx = max(range(len(steps)), key=lambda i: len(steps[i]))
        new_steps = tuple(s for i, s in enumerate(steps) if i != longest_idx)
        # optional LLM advisor may replace new_steps (non-blocking)
        if self._advisor is not None:
            try:
                adv = self._advisor.propose(skill, stats)
                if adv:
                    new_steps = tuple(adv)
            except Exception:
                pass
        return SkillVariant(
            skill_id=skill.skill_id,
            capability=skill.capability,
            new_steps=new_steps,
            version=skill.version + 1,
        )

    # --- ISkillEvaluator -----------------------------------------------------
    def test_in_sandbox(self, variant: SkillVariant,
                       baseline_score: float) -> EvalResult:
        passed = 0
        total = 0
        for step in variant.new_steps:
            total += 1
            try:
                res: ExecutionResult = self._sandbox.execute(
                    step.split(), timeout_sec=self._timeout, label=variant.skill_id
                )
                if res.returncode == 0 and not res.killed:
                    passed += 1
            except Exception:
                # O1: sandbox failure -> step counts as failed, never crashes
                pass
        score = (passed / float(total)) if total else 0.0
        return EvalResult(
            score=score,
            better_than_baseline=score > baseline_score,
            detail=f"{passed}/{total} steps ok",
        )

    # --- closed loop ---------------------------------------------------------
    def evolve_skill(self, skill: Procedure,
                     stats: SkillUsageStats) -> Procedure:
        """Run the full loop; return the (possibly updated) ACTIVE skill.

        If a better variant is found, the new Procedure (version+1, ACTIVE) replaces it in the
        store and the old one is marked SUPERSEDED (kept in history). Otherwise the input skill
        is returned unchanged (no mutation, O1).
        """
        variant = self.propose_improvement(skill, stats)
        if variant is None:
            return skill
        # baseline: score the current skill's steps the same way
        baseline = self._score_current(skill)
        result = self.test_in_sandbox(variant, baseline)
        if not result.better_than_baseline:
            return skill  # keep old (not better)
        new_skill = replace(
            skill,
            steps=variant.new_steps,
            version=variant.version,
            lifecycle=PolicyLifecycle.ACTIVE,
        )
        old_superseded = replace(skill, lifecycle=PolicyLifecycle.SUPERSEDED)
        self._history.setdefault(skill.capability, []).append(old_superseded)
        self._memory.store_skill(new_skill)
        return new_skill

    def _score_current(self, skill: Procedure) -> float:
        """Baseline score of the current skill (same sandbox metric as the variant)."""
        passed = 0
        total = 0
        for step in skill.steps:
            total += 1
            try:
                res = self._sandbox.execute(
                    step.split(), timeout_sec=self._timeout, label=skill.skill_id
                )
                if res.returncode == 0 and not res.killed:
                    passed += 1
            except Exception:
                pass
        return (passed / float(total)) if total else 0.0

    def history(self, capability: str) -> List[Procedure]:
        """SUPERSEDED old versions kept for traceability (ТЗ-EVOLUTION-01)."""
        return list(self._history.get(capability, []))


def build_skill_evolver(sandbox: IExecutionSandbox, memory: IProceduralMemory,
                        min_uses: int = 5, success_threshold: float = 0.8,
                        timeout_sec: float = 5.0, advisor=None) -> "SkillEvolver":
    """Standalone factory (Флаг C) — wire a SkillEvolver over injected ports.

    K6: services -> contracts only; the concrete SubprocessSandbox / InMemoryProceduralMemory
    are supplied by the caller (composition root), never imported here.
    """
    return SkillEvolver(sandbox=sandbox, memory=memory, min_uses=min_uses,
                         success_threshold=success_threshold, timeout_sec=timeout_sec,
                         advisor=advisor)
