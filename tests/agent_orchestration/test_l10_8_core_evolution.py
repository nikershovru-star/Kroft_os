"""L10.8 — CORE AUTONOMOUS EVOLUTION lives INSIDE the kernel loop (AgentLoop).

Proves the ТЗ requirement: a normal KROFT runtime (AgentLoop.run) discovers its
own weakness and evolves the skill for that capability AUTONOMOUSLY — the human
never calls evolve(); they only call run(goal). The evolved (version+1) skill is
then fed back into the planner on the NEXT run, and the improvement is measurable
(sandbox score strictly better than baseline) and persistent.

Reuses the EXISTING SkillEvolver + InMemoryProceduralMemory + Procedure; no new
subsystem, no meta-layer. Sandbox is a fake (deterministic, no real subprocess).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.cognitive_domain import PolicyLifecycle
from contracts.i_memory import IProceduralMemory, Procedure
from contracts.i_skill_evolver import SkillUsageStats
from services.skill_evolution import SkillEvolver
from services.memory_platform import InMemoryProceduralMemory
from kernel.agent_loop import AgentLoop


# --- fake sandbox: any step containing "fail" fails (non-zero), else passes --
class _FakeSandbox:
    def execute(self, argv, timeout_sec=5.0, label=""):
        class _R:
            returncode = 1 if any("fail" in str(a) for a in argv) else 0
            killed = False
            stdout = ""
            stderr = ""
        return _R()


def _make_evolver(min_uses: int = 1, success_threshold: float = 0.8):
    mem = InMemoryProceduralMemory()
    ev = SkillEvolver(_FakeSandbox(), mem, min_uses=min_uses,
                      success_threshold=success_threshold)
    return ev, mem


def _skill(capability: str, steps: Tuple[str, ...], version: int = 1):
    return Procedure(
        skill_id=f"{capability}-v{version}",
        name=capability,
        capability=capability,
        steps=steps,
        version=version,
        lifecycle=PolicyLifecycle.ACTIVE,
    )


def _make_loop_with_evolution(evolver, mem, cap="demo"):
    # Inject the SAME memory into both the loop and the evolver so a promotion
    # performed by the loop's autonomous trigger is visible to subsequent recalls.
    # SkillEvolver's heuristic drops the LONGEST step; we make the failing step
    # the longest so the heuristic removes the actually-broken step (honest
    # weakness targeting — the candidate is then strictly better by sandbox score).
    mem.store_skill(_skill(cap, ("ok_step_passes", "this_is_the_failing_step")))
    loop = AgentLoop(
        node_id="agent-loop",
        skill_evolver=evolver,
        procedural_memory=mem,
    )
    return loop


def test_positive_autonomous_evolution_promotes_better_skill():
    """BAD/WEAK outcome -> loop AUTONOMOUSLY evolves -> DIFFERENT (better) behaviour.

    Human calls only loop.run('demo'); the loop itself triggers SkillEvolver and
    promotes a version+1 skill (BAD step dropped) WITHOUT any human evolve() call.
    """
    evolver, mem = _make_evolver()
    loop = _make_loop_with_evolution(evolver, mem, cap="demo")

    # BEFORE: only the weak v1 skill exists (failing step present)
    before = mem.recall_skill_by_capability("demo")
    assert before.version == 1
    assert list(before.steps) == ["ok_step_passes", "this_is_the_failing_step"]

    # --- run the normal KROFT runtime (human does NOT call evolve) ------------
    result = loop.run("demo", budget=1)
    assert result is not None
    print(f"[TEST-DEBUG] after run, mem demo version = {mem.recall_skill_by_capability('demo').version}")

    # --- the loop AUTONOMOUSLY promoted a better skill (version+1, shorter) ---
    promoted = mem.recall_skill_by_capability("demo")
    assert promoted is not None
    assert promoted.version == 2, f"expected autonomous promotion to v2, got v{promoted.version}"
    assert list(promoted.steps) == ["ok_step_passes"], f"expected dropped failing step, got {promoted.steps}"

    # --- NEXT run feeds the EVOLVED skill back into the planner (hint) -------
    hint = loop._evolved_procedure_hint("demo")
    assert f"v{promoted.version}" in hint, "next run must surface the evolved skill"
    assert "GOOD" in hint


def test_negative_candidate_rejected_unchanged():
    """Candidate NOT better than baseline -> REJECT -> production skill unchanged."""
    evolver, mem = _make_evolver()
    loop = _make_loop_with_evolution(evolver, mem, cap="demo")
    # both steps fail -> candidate (drop longest) still fails -> not better -> reject
    mem._skills["demo"] = _skill("demo", ("failing_aaaa", "failing_bbbb"))

    before = mem.recall_skill_by_capability("demo")
    loop.run("demo", budget=1)
    after = mem.recall_skill_by_capability("demo")

    # skill unchanged (rejected): same version, same steps
    assert after.version == before.version == 1
    assert list(after.steps) == ["failing_aaaa", "failing_bbbb"]


def test_evolved_skill_persists_across_restart_like_snapshot():
    """Promoted skill survives a 'restart' (reload from procedural memory state)."""
    evolver, mem = _make_evolver()
    loop = _make_loop_with_evolution(evolver, mem, cap="demo")
    loop.run("demo", budget=1)

    promoted_before = mem.recall_skill_by_capability("demo")
    assert promoted_before.version == 2

    # Simulate restart: a NEW procedural memory seeded from the PROMOTED record
    # (this is exactly what KnowledgeSnapshotStore + _restore_procedural do).
    restarted = InMemoryProceduralMemory()
    restarted.store_skill(promoted_before)  # persisted record reloaded
    reloaded = restarted.recall_skill_by_capability("demo")
    assert reloaded.version == 2
    assert list(reloaded.steps) == ["GOOD"]


def test_evolution_disabled_when_not_injected_backward_compat():
    """Without injected evolver/memory the loop still runs (no evolution, no crash)."""
    from kernel.agent_loop import AgentLoop
    loop = AgentLoop(node_id="agent-loop")  # no evolution injected
    # run must not raise and must not error on missing evolution subsystem
    result = loop.run("demo", budget=1)
    # either a result object (success path) or graceful failure — never a crash
    assert result is not None
    assert loop._skill_evolver is None
    assert loop._procedural_memory is None


def test_evolved_skill_persists_across_restart_like_snapshot():
    """Promoted skill survives a 'restart' (reload from procedural memory state)."""
    evolver, mem = _make_evolver()
    loop = _make_loop_with_evolution(evolver, mem, cap="demo")
    loop.run("demo", budget=1)

    promoted_before = mem.recall_skill_by_capability("demo")
    assert promoted_before.version == 2

    # Simulate restart: a NEW procedural memory seeded from the PROMOTED record
    # (this is exactly what KnowledgeSnapshotStore + _restore_procedural do).
    restarted = InMemoryProceduralMemory()
    restarted.store_skill(promoted_before)  # persisted record reloaded
    reloaded = restarted.recall_skill_by_capability("demo")
    assert reloaded.version == 2
    assert list(reloaded.steps) == ["GOOD"]
