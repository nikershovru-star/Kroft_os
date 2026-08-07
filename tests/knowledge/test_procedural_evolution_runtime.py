"""ТЗ-PHASE-L: Procedural Evolution Runtime — SkillEvolver wired to the real loop.

Targeted proof (K5 + I-09): after real ticks the per-skill procedure stats
(runs/successes) accumulate from CognitiveKernel._outcomes (not fake stats); when the
real success rate is low, SkillEvolver evolves the matching skill to a new version
written into InMemoryProceduralMemory; after a cold boot WITHOUT the vault the evolved
skill + accumulated stats restore from KnowledgeSnapshotStore. Reuses CognitiveKernel.
tick, SkillEvolver, ProceduralMemory, KnowledgeSnapshotStore; no new port/layer/DTO (K5/K6).
"""

from __future__ import annotations

import os

from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import ExecutionOutcome, ConfidenceScore


def test_real_tick_stats_accumulate(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "l.json")

    a = KroftApp(KroftConfig(node_id="l1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    # 3 real demo ticks -> procedural runs accumulate from REAL outcomes (PHASE L)
    for _ in range(3):
        a.step()
    assert a.procedural._procedures["demo"]["runs"] >= 3
    assert os.path.exists(snap)  # PHASE K: persisted immediately


def test_low_success_rate_evolves_skill_and_persists(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "l2.json")

    a = KroftApp(KroftConfig(node_id="l1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    before_v = a.procedural._skills["demo"].version
    # simulate failed ticks -> SkillEvolver evolves demo skill to a new version
    a.kernel._outcomes = [
        ExecutionOutcome(episode_id="f1", success=False, utility=0.0,
                         confidence=ConfidenceScore(0.5, "observation"), causal=None),
        ExecutionOutcome(episode_id="f2", success=False, utility=0.0,
                         confidence=ConfidenceScore(0.5, "observation"), causal=None),
    ]
    a._evolve_procedural_from_runtime(capability="demo", skill=a.procedural._skills["demo"])
    after_v = a.procedural._skills["demo"].version
    assert after_v > before_v
    a._save_knowledge()

    # cold boot without vault -> evolved skill + accumulated stats restored
    b = KroftApp(KroftConfig(node_id="l2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    assert b.procedural._skills["demo"].version == after_v
    assert b.procedural._procedures["demo"]["runs"] >= 1
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 0.97) < 1e-9
