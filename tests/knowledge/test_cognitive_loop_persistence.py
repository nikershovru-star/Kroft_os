"""ТЗ-PHASE-K: Runtime Cognitive Loop persistence closure.

Targeted proof (K5 + I-09): a single KroftApp.step() runs CognitiveKernel.tick +
SkillEvolver and now persists IMMEDIATELY (no explicit query needed). After a cold
boot WITHOUT the vault, the evolved memory (episode from the tick + demo skill
evolved to v2) is restored, while graph/trust stay intact. Reuses the existing
_save_knowledge path; no new port/layer/DTO (K5/K6).
"""

from __future__ import annotations

import json
import os

from composition.run_kroft import KroftApp, KroftConfig


def test_step_persists_and_restores_evolved_memory(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    a = KroftApp(KroftConfig(node_id="k1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    a.step()  # tick + evolve + immediate persist (ТЗ-PHASE-K)

    # step() alone wrote the snapshot (no explicit query)
    assert os.path.exists(snap)
    blob = json.load(open(snap, encoding="utf-8"))
    assert len(blob.get("episodes", [])) >= 1
    assert blob["procedural"]["skills"]["demo"]["version"] == 2  # SkillEvolver outcome

    # cold boot without vault -> evolved memory restored
    b = KroftApp(KroftConfig(node_id="k2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    assert len(b.memory._episodes) >= 1
    assert b.procedural._skills["demo"].version == 2
    # graph/trust untouched (trust stays at demo seed 0.97)
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 0.97) < 1e-9
