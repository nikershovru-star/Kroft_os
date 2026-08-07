"""ТЗ-PHASE-E: Persistent Evolution Memory — TrustRegistry survives restart.

Targeted proof (K5 + I-09): mutate a TrustRegistry's running trust, persist it
inside the knowledge snapshot, cold-boot WITHOUT the vault (snapshot only), and
assert the running trust is restored exactly and the graph/index stay intact.
Reuses the same direct-assignment replay pattern as run_evolution.py (no new
port/layer — composition-only wiring into KnowledgeSnapshotStore).
"""

from __future__ import annotations

import json

from composition.run_kroft import KroftApp, KroftConfig


def _mutate_trust(app):
    # simulate accumulated dispatch experience moving trust off the demo seed
    app.trust.record_outcome("agent.research", success=True)    # 0.97 -> 1.0 (cap)
    app.trust.record_outcome("agent.programmer", success=False)  # 0.97 -> 0.87
    app.trust.record_outcome("agent.architect", success=False)   # 0.97 -> 0.87
    app.trust.record_outcome("agent.planner", success=False)     # 0.97 -> 0.87
    return dict(app.trust._running)


def test_trust_persists_and_restores(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent here", encoding="utf-8")
    snap = str(tmp_path / "k.json")

    # Run 1: boot with vault, mutate trust, save
    a = KroftApp(KroftConfig(node_id="t1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    saved = _mutate_trust(a)
    a._save_knowledge()

    # snapshot file carries the trust field and it matches
    with open(snap, encoding="utf-8") as fh:
        blob = json.load(fh)
    assert "trust" in blob
    assert blob["trust"] == {k: saved[k] for k in saved}

    # Run 2: COLD boot without vault -> trust restored exactly
    b = KroftApp(KroftConfig(node_id="t2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    restored = dict(b.trust._running)
    assert set(restored) == set(saved)
    for k in saved:
        assert abs(restored[k] - saved[k]) < 1e-9
    # graph/index still intact (trust addition didn't corrupt them)
    assert len(b.graph.nodes()) >= 1
    # restored trust is actually queryable (used by AgentRuntime gating)
    assert abs(b.trust.current_trust("agent.research") - saved["agent.research"]) < 1e-9
