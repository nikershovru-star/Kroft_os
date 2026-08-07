"""ТЗ-PHASE-I: Persistence Convergence — run_evolution resumes from the unified snapshot.

Targeted proof (K5 + I-09): build a KnowledgeSnapshot via KroftApp (run_kroft
format), then load it into run_evolution._LivingCore via the --knowledge-snapshot
path, and assert episodes/semantic/normative/skills/trust resume from the SAME
file (no second divergent format). Also proves the legacy JsonMemoryStore path
still writes its own kernel_state.json when the flag is omitted. Reuses the
existing _episode_from_dict / _semantic_from_dict / _policy_from_dict /
_procedure_from_dict converters (no new serializer/DTO/port).
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


def test_evolution_resumes_from_unified_snapshot(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")
    state_dir = str(tmp_path / "kroft_state")

    # build a run_kroft snapshot carrying all layers
    a = KroftApp(KroftConfig(node_id="i1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    a.memory._semantic = [
        SemanticFact(id="sf-1", content="LAW K1 forbids kernel->contracts imports",
                     confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
                     causal=None, source_episodes=("ep-a1",)),
    ]
    a.memory._normative = [
        Policy(id="pol-1", name="no-hard-mutation", layer="soft",
               body="Runtime tuning only changes SOFT layers",
               confidence=ConfidenceScore(0.8, ProvenanceType.AGGREGATION),
               provenance=Provenance(source="reflection", actor="kernel"),
               lifecycle=PolicyLifecycle.ACTIVE),
    ]
    a.memory._episodes = [Episode(id="ep-a1", summary="audit done",
                                  confidence=ConfidenceScore(0.6, ProvenanceType.AGGREGATION),
                                  provenance=Provenance(source="test", actor="kernel"))]
    a.trust.record_outcome("agent.research", success=True)
    a._save_knowledge()
    kroft = (len(a.memory._episodes), len(a.memory._semantic), len(a.memory._normative),
             round(a.trust.current_trust("agent.research"), 4), len(a.procedural._skills))

    # convergence: run_evolution resumes from the SAME snapshot file
    core = _LivingCore(state_dir=state_dir, node_id="i2", llm_client=None, ticks=0,
                       autosave_sec=0.0, bg_consolidate=False, knowledge_snapshot=snap)
    ev = (len(core.mem._episodes), len(core.mem._semantic), len(core.mem._normative),
          round(core.trust.current_trust("agent.research"), 4), len(core.proc._skills))
    assert ev == kroft and ev[0] >= 1

    # legacy path still writes its own kernel_state.json when flag omitted
    legacy = _LivingCore(state_dir=state_dir, node_id="i3", llm_client=None, ticks=0,
                         autosave_sec=0.0, bg_consolidate=False, knowledge_snapshot=None)
    legacy.save()
    assert os.path.exists(os.path.join(state_dir, "kernel_state.json"))
