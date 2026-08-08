"""Slice 4 — experience-informed plan ranking (proof).

Proof (K5): ReferencePlanner accepts an optional procedural memory and biases the
confidence of candidates that carry a structured execution intent (file/command) by
the capability's past success_rate. A capability with proven success ranks HIGHER
than the same capability with no experience (baseline). Unknown capability -> unchanged.
Abstract deliberation (no execution_steps) is untouched (determinism preserved).

Reuses InMemoryProceduralMemory._procedures (runs/successes/success_rate) via the
public KroftApp.procedural; drives real file actions through KroftApp.step to build
experience. No new port/DTO/layer; only kernel/planning.py changed.
"""

from __future__ import annotations

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import (
    Goal, Intent, ConfidenceScore, Provenance, WorldState,
)
from kernel.planning import ReferencePlanner


def _make_app(tmp_path, snapshot):
    app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                               vault=str(tmp_path / "vault"),
                               knowledge_snapshot=str(snapshot)))
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    return app


def _best_with_exec(tmp_path, planner, goal_text):
    goal = Goal(id="g", intent_id="i1", description=goal_text,
                confidence=ConfidenceScore(0.8), provenance=Provenance(source="intent", actor="kernel"))
    intent = Intent(id="i1", text=goal_text, confidence=ConfidenceScore(0.8),
                    provenance=Provenance(source="intent", actor="kernel"))
    cands = planner.plan(goal, [], WorldState(node_id="n1"), 100, intent=intent)
    exec_cands = [c for c in cands if c.execution_steps]
    assert exec_cands, "planner must emit execution_steps for a file/command goal"
    return max(exec_cands, key=lambda c: c.confidence.value)


def test_experience_raises_confidence_above_baseline(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # build real experience: N successful file actions
    for _ in range(3):
        app.step("запиши hello в x.txt")
    _proc = app.procedural._procedures["exec:file"]
    assert _proc["runs"] >= 3 and _proc["successes"] == _proc["runs"], _proc

    # experienced planner vs baseline (no procedural memory)
    exp = ReferencePlanner(clock=None, procedural=app.procedural)
    base = ReferencePlanner(clock=None)

    best_exp = _best_with_exec(tmp_path, exp, "запиши world в y.txt")
    best_base = _best_with_exec(tmp_path, base, "запиши world в y.txt")

    assert best_exp.confidence.value > best_base.confidence.value, (
        best_exp.confidence.value, best_base.confidence.value)


def test_unknown_capability_unchanged(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)
    app.step("запиши hello в x.txt")  # only exec:file is known

    exp = ReferencePlanner(clock=None, procedural=app.procedural)
    base = ReferencePlanner(clock=None)

    # a command goal for an UNKNOWN capability (no exec:unknowncmd in memory)
    best_exp = _best_with_exec(tmp_path, exp, "выполни unknowncmd123")
    best_base = _best_with_exec(tmp_path, base, "выполни unknowncmd123")

    assert abs(best_exp.confidence.value - best_base.confidence.value) < 1e-9
