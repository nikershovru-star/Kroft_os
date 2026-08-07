"""ТЗ-PHASE-G: Persistent Episodic Memory — recorded Episodes survive restart.

Targeted proof (K5 + I-09): record several Episode objects into the layered
memory, persist them inside the knowledge snapshot, cold-boot WITHOUT the vault,
and assert the episode count + full content (id/summary/confidence/provenance)
match exactly, while graph/trust/procedural stay intact. Reuses the existing
_episode_to_dict / _episode_from_dict converters (no new serializer/DTO/port).
"""

from __future__ import annotations

import json

from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType


def _make_episodes():
    return [
        Episode(id="ep-a1", summary="agent.research completed LAW audit",
                confidence=ConfidenceScore(0.92, ProvenanceType.AGGREGATION),
                provenance=Provenance(source="agent:research", actor="agent.research",
                                      timestamp="2026-08-07T10:00:00Z")),
        Episode(id="ep-b2", summary="SkillEvolver promoted demo.v2",
                confidence=ConfidenceScore(0.75, ProvenanceType.AGGREGATION),
                provenance=Provenance(source="skill_evolver", actor="kernel",
                                      timestamp="2026-08-07T10:05:00Z")),
        Episode(id="ep-c3", summary="trust decayed for agent.programmer",
                confidence=ConfidenceScore(0.4, ProvenanceType.AGGREGATION),
                provenance=Provenance(source="agent:programmer", actor="agent.programmer",
                                      timestamp="2026-08-07T10:10:00Z")),
    ]


def _ep_state(app):
    return [(e.id, e.summary, round(e.confidence.value, 4), e.provenance.source,
             e.provenance.actor, e.provenance.timestamp) for e in app.memory._episodes]


def test_episodic_persists_and_restores(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    a = KroftApp(KroftConfig(node_id="g1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    a.memory._episodes = _make_episodes()
    a.trust.record_outcome("agent.research", success=True)
    saved = _ep_state(a)
    a._save_knowledge()

    # snapshot carries the episodes block
    with open(snap, encoding="utf-8") as fh:
        blob = json.load(fh)
    assert "episodes" in blob and len(blob["episodes"]) == 3

    # cold boot without vault -> restore
    b = KroftApp(KroftConfig(node_id="g2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    restored = _ep_state(b)

    assert len(restored) == len(saved) == 3
    assert restored == saved  # exact: id/summary/confidence/provenance
    # graph/trust/procedural untouched
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 1.0) < 1e-9
    assert len(b.procedural._skills) >= 1
