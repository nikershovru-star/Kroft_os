"""ТЗ-PHASE-J: Persistence Write Convergence — run_evolution writes back to the SAME snapshot.

Targeted proof (K5 + I-09): build a run_kroft snapshot (with a real graph), load it
into run_evolution._LivingCore via --knowledge-snapshot, mutate semantic/policy/
episode/trust/skill, call save(), and assert:
  - the SAME snapshot file changed (write convergence),
  - the prior graph/index is PRESERVED (not clobbered by run_evolution),
  - kernel_state.json did NOT appear (no second source of truth),
  - the legacy path (no flag) still writes kernel_state.json.
Reuses existing converters (_episode_to_dict / _semantic_to_dict / _policy_to_dict /
_procedure_to_dict); no new serializer/DTO/port/storage class.
"""

from __future__ import annotations

import json
import os

from composition.run_kroft import KroftApp, KroftConfig
from run_evolution import _LivingCore
from contracts.cognitive_domain import (
    SemanticFact, Policy, Episode, ConfidenceScore, Provenance,
    ProvenanceType, PolicyLifecycle,
)
from contracts.i_memory import Procedure


def test_evolution_writes_back_to_unified_snapshot(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")
    state_dir = str(tmp_path / "kroft_state")

    # build a run_kroft snapshot carrying a real graph + one semantic fact
    a = KroftApp(KroftConfig(node_id="j1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    a.memory._semantic = [SemanticFact(id="sf-1", content="old fact",
                                       confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION),
                                       causal=None, source_episodes=())]
    a._save_knowledge()
    graph_before = len(json.load(open(snap, encoding="utf-8"))["graph"].get("nodes", []))

    # run_evolution resumes from + writes back into the SAME snapshot
    core = _LivingCore(state_dir=state_dir, node_id="j2", llm_client=None, ticks=0,
                       autosave_sec=0.0, bg_consolidate=False, knowledge_snapshot=snap)
    core.mem._semantic = [SemanticFact(id="sf-2", content="evolved fact",
                                       confidence=ConfidenceScore(0.95, ProvenanceType.AGGREGATION),
                                       causal=None, source_episodes=("ep-x",))]
    core.mem._normative = [Policy(id="pol-2", name="evolved-policy", layer="soft",
                                  body="evolved body", confidence=ConfidenceScore(0.85, ProvenanceType.AGGREGATION),
                                  provenance=Provenance(source="reflection", actor="kernel"),
                                  lifecycle=PolicyLifecycle.ACTIVE)]
    core.mem._episodes = [Episode(id="ep-x", summary="evolved episode",
                                  confidence=ConfidenceScore(0.7, ProvenanceType.AGGREGATION),
                                  provenance=Provenance(source="test", actor="kernel"))]
    core.trust.record_outcome("agent.research", success=True)
    core.proc.store_skill(Procedure(skill_id="ev.sk", name="ev", capability="ev.cap",
                                    steps=("do x",), confidence=0.6))
    core.save()

    blob = json.load(open(snap, encoding="utf-8"))
    assert any(f["content"] == "evolved fact" for f in blob["semantic"])
    assert any(p["name"] == "evolved-policy" for p in blob["normative"])
    assert any(e["id"] == "ep-x" for e in blob["episodes"])
    assert blob["trust"].get("agent.research") == 1.0
    assert "ev.cap" in blob["procedural"]["skills"]
    # graph preserved (run_evolution does not clobber it)
    assert len(blob["graph"].get("nodes", [])) == graph_before and graph_before > 0
    # no second source of truth
    assert not os.path.exists(os.path.join(state_dir, "kernel_state.json"))

    # legacy path (no flag) still writes its own kernel_state.json
    legacy = _LivingCore(state_dir=state_dir, node_id="j3", llm_client=None, ticks=0,
                         autosave_sec=0.0, bg_consolidate=False, knowledge_snapshot=None)
    legacy.save()
    assert os.path.exists(os.path.join(state_dir, "kernel_state.json"))
