"""ADR-028 Stage 2 — Abstraction sidecar (compression without loss).

Proof-over-existence: consolidation of N episodes yields a fact whose sidecar
maps back to EXACTLY those N episode ids, and the mapping survives a
save/load round-trip through KnowledgeSnapshotStore (the 9th layer).
"""

import os
import tempfile

from contracts.cognitive_domain import ConfidenceScore, Episode, NodeLamportClock, Provenance, ProvenanceType
from contracts.i_memory_evolution import IMemoryEvolution
from kernel.memory_evolution import ReferenceMemoryEvolution
from composition.knowledge_persistence import KnowledgeSnapshotStore


def _ep(ep_id, summary, conf=0.9):
    return Episode(id=ep_id, summary=summary,
                   confidence=ConfidenceScore(conf, ProvenanceType.OBSERVATION),
                   provenance=Provenance(source="s", actor="s"))


def test_consolidation_sidecar_maps_fact_to_exact_episodes():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "user prefers Y") for i in range(3)]
    sidecar = me.consolidation_sidecar(eps)
    # exactly one fact for the repeated group
    assert len(sidecar) == 1
    fact_id, source_ids = next(iter(sidecar.items()))
    assert source_ids == [f"e{i}" for i in range(3)]
    assert len(source_ids) == 3


def test_sidecar_survives_snapshot_roundtrip():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "user prefers Y") for i in range(3)]
    sidecar = me.consolidation_sidecar(eps)
    assert sidecar  # non-empty before persistence

    tmp = os.path.join(tempfile.gettempdir(), "adr028_sidecar_test.json")
    try:
        store = KnowledgeSnapshotStore(tmp)
        store.save(graph_state={}, index_state={}, abstraction_sidecar=sidecar)
        loaded = store.load_abstraction_sidecar()
        assert loaded == sidecar, "sidecar link fact->episodes lost on round-trip"
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def test_sidecar_deterministic_for_same_input():
    me = ReferenceMemoryEvolution(NodeLamportClock("N"), 0.7, 2)
    eps = [_ep(f"e{i}", "user prefers Y") for i in range(3)]
    a = me.consolidation_sidecar(eps)
    b = me.consolidation_sidecar(eps)
    assert a == b  # I-09: identical input -> identical mapping


def test_port_contract_has_sidecar_method():
    # the new capability is part of the port, not just the reference impl
    assert "consolidation_sidecar" in IMemoryEvolution.__dict__["__abstractmethods__"] or \
           callable(getattr(IMemoryEvolution, "consolidation_sidecar", None))
