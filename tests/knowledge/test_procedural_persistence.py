"""ТЗ-PHASE-F: Persistent Procedural Memory — skills + usage stats survive restart.

Targeted proof (K5 + I-09): evolve a skill via SkillEvolver, persist it inside the
knowledge snapshot, cold-boot WITHOUT the vault, and assert the evolved skill
(version + steps) + procedure stats are restored exactly, with no duplication,
while the graph and trust stay intact. Reuses the existing _procedure_to_dict /
_procedure_from_dict converters (dataclasses.replace re-attaches version/lifecycle
that the base converter drops — no new port/layer/DTO).
"""

from __future__ import annotations

import json

from composition.run_kroft import KroftApp, KroftConfig
from contracts.i_skill_evolver import SkillUsageStats


def _skill_state(app):
    return {
        "skills": {c: (list(s.steps), s.version, round(s.confidence, 4))
                   for c, s in app.procedural._skills.items()},
        "procedures": {k: (v["runs"], v["successes"], round(v["success_rate"], 4))
                       for k, v in app.procedural._procedures.items()},
    }


def test_procedural_persists_and_restores(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    # Run 1: evolve the seeded demo skill -> version 2, then save
    a = KroftApp(KroftConfig(node_id="f1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    a.evolver.evolve_skill(
        a._demo_skill, SkillUsageStats(capability="demo", uses=10, success_rate=0.3))
    a.trust.record_outcome("agent.research", success=True)
    saved = _skill_state(a)
    a._save_knowledge()

    # snapshot carries the procedural block with the evolved skill
    with open(snap, encoding="utf-8") as fh:
        blob = json.load(fh)
    assert "procedural" in blob and "skills" in blob["procedural"]
    assert blob["procedural"]["skills"]["demo"]["version"] == 2

    # Run 2: COLD boot without vault -> restore
    b = KroftApp(KroftConfig(node_id="f2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    restored = _skill_state(b)

    # exact match + no duplication
    assert saved["skills"] == restored["skills"]
    assert saved["procedures"] == restored["procedures"]
    assert len(restored["skills"]) == len(saved["skills"])
    # graph + trust untouched
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 1.0) < 1e-9
    # restored skill is actually usable (recall returns the evolved version)
    recalled = b.procedural.recall_skill_by_capability("demo")
    assert recalled is not None and recalled.version == 2
