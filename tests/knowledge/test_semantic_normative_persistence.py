"""ТЗ-PHASE-H: Persistent Semantic + Normative Memory survive restart.

Targeted proof (K5 + I-09): record SemanticFacts + Policies into the layered
memory, persist them inside the knowledge snapshot, cold-boot WITHOUT the vault,
and assert the facts + policies are restored exactly (id/content/confidence/
source_episodes / layer / lifecycle) while graph/trust/procedural/episodic stay
intact. Reuses the existing _semantic_to_dict/_semantic_from_dict and
_policy_to_dict/_policy_from_dict converters (no new serializer/DTO/port).
"""

from __future__ import annotations

import json

from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import (
    SemanticFact, Policy, ConfidenceScore, Provenance, ProvenanceType, PolicyLifecycle,
)


def _make():
    facts = [
        SemanticFact(id="sf-1",
                     content="LAW K1 forbids cross-layer imports from kernel into contracts",
                     confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
                     causal=None, source_episodes=("ep-a1", "ep-b2")),
        SemanticFact(id="sf-2", content="Graph engine restores byte-stable across restarts",
                     confidence=ConfidenceScore(0.7, ProvenanceType.AGGREGATION),
                     causal=None, source_episodes=("ep-c3",)),
    ]
    policies = [
        Policy(id="pol-1", name="no-hard-mutation", layer="soft",
               body="Runtime tuning only changes SOFT layers",
               confidence=ConfidenceScore(0.8, ProvenanceType.AGGREGATION),
               provenance=Provenance(source="reflection", actor="kernel"),
               lifecycle=PolicyLifecycle.ACTIVE),
    ]
    return facts, policies


def _fact_state(app):
    return [(f.id, f.content, round(f.confidence.value, 4), list(f.source_episodes))
            for f in app.memory._semantic]


def _pol_state(app):
    return [(p.id, p.name, p.layer, round(p.confidence.value, 4), p.lifecycle.name)
            for p in app.memory._normative]


def test_semantic_normative_persist_and_restore(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    a = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    facts, policies = _make()
    a.memory._semantic = facts
    a.memory._normative = policies
    a.trust.record_outcome("agent.research", success=True)
    saved_f = _fact_state(a)
    saved_p = _pol_state(a)
    a._save_knowledge()

    with open(snap, encoding="utf-8") as fh:
        blob = json.load(fh)
    assert "semantic" in blob and len(blob["semantic"]) == 2
    assert "normative" in blob and len(blob["normative"]) == 1

    b = KroftApp(KroftConfig(node_id="h2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    restored_f = _fact_state(b)
    restored_p = _pol_state(b)

    assert restored_f == saved_f  # exact: id/content/confidence/source_episodes
    assert restored_p == saved_p  # exact: id/name/layer/confidence/lifecycle
    # graph/trust/procedural/episodic untouched
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 1.0) < 1e-9
    assert len(b.procedural._skills) >= 1
