"""PHASE H — Шаг 2: layered memory (semantic + normative) survives restart.

Proof (K5 + I-09), mirrors test_learn_by_doing but for the SOFT memory layers:
real components of the live loop -- memory.commit_semantic(...) and
memory.commit_normative(...) (exactly how kernel/research.py, run_evolution.py
and services/distributed_runtime.py feed experience in) -- persist inside the
knowledge snapshot via _save_knowledge(), and a COLD-BOOTED KroftApp (same
snapshot, no vault) restores them into memory.get_semantic()/get_normative().

Reuses the existing _semantic_to_dict/_semantic_from_dict and
_policy_to_dict/_policy_from_dict converters + KnowledgeSnapshotStore. No new
serializer / DTO / port / layer (K5/K6-clean).
"""

from __future__ import annotations

from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import (
    SemanticFact, Policy, ConfidenceScore, Provenance, ProvenanceType, PolicyLifecycle,
)


def test_layered_memory_commit_persist_and_restore(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    # --- live loop writes experience through the PUBLIC commit_* API ---
    a = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))

    a.memory.commit_semantic(SemanticFact(
        id="sf-1",
        content="LAW K1 forbids cross-layer imports from kernel into contracts",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=None, source_episodes=("ep-a1", "ep-b2"),
    ))
    a.memory.commit_semantic(SemanticFact(
        id="sf-2",
        content="Graph engine restores byte-stable across restarts",
        confidence=ConfidenceScore(0.7, ProvenanceType.AGGREGATION),
        causal=None, source_episodes=("ep-c3",),
    ))
    a.memory.commit_normative(Policy(
        id="pol-1", name="no-hard-mutation", layer="soft",
        body="Runtime tuning only changes SOFT layers",
        confidence=ConfidenceScore(0.8, ProvenanceType.AGGREGATION),
        provenance=Provenance(source="reflection", actor="kernel"),
        lifecycle=PolicyLifecycle.ACTIVE,
    ))

    assert len(a.memory.get_semantic()) == 2
    assert len(a.memory.get_normative()) == 1

    a._save_knowledge()

    # --- cold boot: new KroftApp, SAME snapshot, no vault ---
    b = KroftApp(KroftConfig(node_id="h2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))

    restored_facts = {f.id: f for f in b.memory.get_semantic()}
    restored_pols = {p.id: p for p in b.memory.get_normative()}

    # semantic: id + content exact round-trip
    assert "sf-1" in restored_facts and "sf-2" in restored_facts
    assert restored_facts["sf-1"].content == \
        "LAW K1 forbids cross-layer imports from kernel into contracts"
    assert restored_facts["sf-2"].content == \
        "Graph engine restores byte-stable across restarts"
    assert list(restored_facts["sf-1"].source_episodes) == ["ep-a1", "ep-b2"]

    # normative: id + body + layer exact round-trip
    assert "pol-1" in restored_pols
    assert restored_pols["pol-1"].body == "Runtime tuning only changes SOFT layers"
    assert restored_pols["pol-1"].layer == "soft"
    assert restored_pols["pol-1"].lifecycle == PolicyLifecycle.ACTIVE

    # the live-loop entry points are intact (nothing lost on reload)
    assert len(b.memory.get_semantic()) == 2
    assert len(b.memory.get_normative()) == 1
