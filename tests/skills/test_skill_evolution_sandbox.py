"""ТЗ-EVOLUTION-01 (ADR-092) — Skill Evolver K8 tests (Флаг 1b, separate).

Covers: usage>=N + low efficiency -> proposal; usage<N / high efficiency -> no proposal;
sandbox-test (isolated subprocess, O1); better variant -> skill updated (version+1, old
SUPERSEDED in history); not-better -> old kept; determinism (I-09, LLM-free path). K5:
reuses IExecutionSandbox/SubprocessSandbox, Procedure (version/lifecycle), PolicyLifecycle,
InMemoryProceduralMemory — no new sandbox/skill store duplicated.
"""

from __future__ import annotations

from typing import List

import pytest

from adapters.subprocess_sandbox import SubprocessSandbox
from contracts.cognitive_domain import PolicyLifecycle
from contracts.i_memory import Procedure
from contracts.i_skill_evolver import (
    ISkillEvaluator,
    ISkillEvolver,
    SkillUsageStats,
    SkillVariant,
)
from services.memory_platform import InMemoryProceduralMemory
from services.skill_evolution import SkillEvolver, build_skill_evolver


def _evolver(min_uses=3, threshold=0.8):
    return build_skill_evolver(
        SubprocessSandbox(), InMemoryProceduralMemory(),
        min_uses=min_uses, success_threshold=threshold, timeout_sec=5.0,
    )


def _skill(cap="cap", steps=("echo good", "this_step_fails_cmd"), version=1):
    return Procedure(
        skill_id=f"{cap}.v{version}", name=cap, capability=cap,
        steps=steps, version=version, confidence=0.5,
    )


# 1) implements ports
def test_skill_evolver_implements_ports():
    ev = _evolver()
    assert isinstance(ev, ISkillEvolver)
    assert isinstance(ev, ISkillEvaluator)


# 2) usage>=N + low efficiency -> proposal
def test_propose_when_low_efficiency():
    ev = _evolver(min_uses=3, threshold=0.8)
    skill = _skill()
    stats = SkillUsageStats(capability="cap", uses=10, success_rate=0.3)
    var = ev.propose_improvement(skill, stats)
    assert isinstance(var, SkillVariant)
    assert var.version == 2
    # heuristic dropped the failing step
    assert "this_step_fails_cmd" not in var.new_steps


# 3) usage < N -> no proposal
def test_no_propose_below_min_uses():
    ev = _evolver(min_uses=3, threshold=0.8)
    stats = SkillUsageStats(capability="cap", uses=2, success_rate=0.1)
    assert ev.propose_improvement(_skill(), stats) is None


# 4) high efficiency -> no proposal
def test_no_propose_when_efficient():
    ev = _evolver(min_uses=3, threshold=0.8)
    stats = SkillUsageStats(capability="cap", uses=50, success_rate=0.95)
    assert ev.propose_improvement(_skill(), stats) is None


# 5) sandbox-test is isolated + deterministic (O1)
def test_sandbox_test_scores_steps():
    ev = _evolver()
    good = SkillVariant(skill_id="cap.v2", capability="cap",
                        new_steps=("echo good",), version=2)
    res = ev.test_in_sandbox(good, baseline_score=0.0)
    assert res.score == 1.0
    assert res.better_than_baseline is True
    # a failing command scores 0, never raises
    bad = SkillVariant(skill_id="cap.v2", capability="cap",
                       new_steps=("this_command_does_not_exist_xyz",), version=2)
    res2 = ev.test_in_sandbox(bad, baseline_score=0.0)
    assert res2.score == 0.0


# 6) better variant -> skill updated (version+1, old SUPERSEDED)
def test_evolve_updates_when_better():
    ev = _evolver(min_uses=3, threshold=0.8)
    skill = _skill()  # has failing step -> baseline score 0
    mem = ev._memory
    mem.store_skill(skill)
    stats = SkillUsageStats(capability="cap", uses=10, success_rate=0.3)
    updated = ev.evolve_skill(skill, stats)
    assert updated.version == 2
    assert updated.lifecycle == PolicyLifecycle.ACTIVE
    assert "this_step_fails_cmd" not in updated.steps
    # old marked SUPERSEDED in history (traceability)
    hist = ev.history("cap")
    assert len(hist) == 1
    assert hist[0].version == 1
    assert hist[0].lifecycle == PolicyLifecycle.SUPERSEDED
    # active recall returns the new version
    assert mem.recall_skill_by_capability("cap").version == 2


# 7) not-better -> old kept unchanged
def test_evolve_keeps_when_not_better():
    ev = _evolver(min_uses=3, threshold=0.8)
    # all steps succeed -> baseline score 1.0; variant also succeeds -> not strictly better
    skill = Procedure(skill_id="cap.v1", name="cap", capability="cap",
                      steps=("echo a", "echo b"), version=1, confidence=0.9)
    mem = ev._memory
    mem.store_skill(skill)
    stats = SkillUsageStats(capability="cap", uses=10, success_rate=0.5)
    updated = ev.evolve_skill(skill, stats)
    # propose may drop a step, but test scores equal -> not better -> original returned
    assert updated.version == 1
    assert updated.lifecycle == PolicyLifecycle.ACTIVE
    assert ev.history("cap") == []


# 8) determinism (I-09, LLM-free path)
def test_deterministic():
    ev = _evolver(min_uses=3, threshold=0.8)
    skill = _skill()
    stats = SkillUsageStats(capability="cap", uses=10, success_rate=0.3)
    a = ev.evolve_skill(skill, stats)
    b = ev.evolve_skill(_skill(), stats)
    assert a.version == b.version
    assert a.steps == b.steps


# 9) Procedure now carries version + lifecycle (K5 extension reused by evolver)
def test_procedure_versioning_fields():
    p = Procedure(skill_id="x", name="x", capability="x", steps=("a",))
    assert p.version == 1
    assert p.lifecycle == PolicyLifecycle.ACTIVE
