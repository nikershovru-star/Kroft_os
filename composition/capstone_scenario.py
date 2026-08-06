"""Capstone scenario runner — distributed self-evolution end-to-end (ТЗ-CAPSTONE-02, ADR-095, Флаг C).

Stands up the two-node capstone (build_distributed_capstone), runs the full joint loop:
  A improves a low-efficiency skill (SkillEvolver) -> packages the improved, signed version
  (SkillPackager) -> replicates to B (SkillDistributor) -> B verifies + trust-gates + installs
  (SkillRepository) -> B USES the installed skill, so its BEHAVIOR changes from the improved skill.

Determinism (I-09): the LLM-free evolver + HMAC signing are reproducible, so the scenario yields
the same evolved version + B behavior on every run (verified by the determinism test).

Флаг C: composition only, NOT wired into build_kernel.
"""

from __future__ import annotations

from contracts.i_memory import Procedure
from contracts.i_skill_evolver import SkillUsageStats

from composition.capstone_distributed import build_distributed_capstone


def run_capstone_scenario(author: str = "alice",
                          bad_step: str = "exit 1 # this-step-fails",
                          good_step: str = "echo good") -> dict:
    """Run the end-to-end distributed self-evolution scenario; return observable outcomes.

    Returns a dict with: evolved_version (A's improved version), behavior_b (B's success rate
    after replication; None if the skill was never installed), installed_b_version (B's installed
    skill version), installed_b_steps (B's installed skill steps).
    """
    node_a, node_b = build_distributed_capstone(author=author)

    # A starts with a skill whose one step reliably fails (low efficiency).
    v1 = Procedure(
        skill_id="cap.v1", name="cap", capability="cap",
        steps=(good_step, bad_step), version=1, confidence=0.9,
    )
    # Usage telemetry shows low success -> triggers improvement on A.
    stats = SkillUsageStats(capability="cap", uses=10, success_rate=0.4)

    evolved = node_a.evolve_and_publish(v1, stats)

    # B behavior AFTER replication (None before; improved success rate after).
    behavior_b = node_b.use_skill("cap")
    installed = node_b.repo._installed.get("cap")

    return {
        "evolved_version": evolved.version,
        "behavior_b": behavior_b,
        "installed_b_version": installed.version if installed is not None else None,
        "installed_b_steps": installed.steps if installed is not None else None,
        "node_b": node_b,
        "node_a": node_a,
    }
