"""Slice 3 (D3) — autonomous planner emits REAL execution intent, end-to-end.

Proof: a natural-language goal (no structured markers, no manual plan injection)
flows through the PUBLIC entry point KroftApp.step(goal_text) -> CognitiveKernel.tick
-> ReferencePlanner recognises the file/command intent from the goal text (D3 fix in
kernel/planning.py) -> Plan.execution_steps carries it -> Execute-phase builds the
JSON payload (P.3) -> RealWorldExecutor performs the REAL action -> file appears on
disk, outcome feeds procedural memory, and the experience survives restart + reuse.

Reuses existing components (K5): RealWorldExecutor, CognitiveKernel._outcomes,
SkillEvolver, InMemoryProceduralMemory, KnowledgeSnapshotStore. No new port/DTO/layer.
"""

from __future__ import annotations

import os

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig


def _make_app(tmp_path, snapshot):
    app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                               vault=str(tmp_path / "vault"),
                               knowledge_snapshot=str(snapshot)))
    # wire the REAL executor confined to the temp dir (K3-clean: reuse public API)
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    return app


def test_autonomous_file_goal_creates_file_and_learns(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # PUBLIC entry point, NO manual plan / execution_steps injection
    app.step("запиши hello в x.txt")

    # 1) the REAL file action happened — file exists on disk
    fpath = tmp_path / "x.txt"
    assert fpath.exists(), "planner-driven file action did not create the file"
    assert fpath.read_text(encoding="utf-8") == "hello"

    # 2) the real outcome was recorded by the kernel loop
    assert app.kernel._outcomes, "no ExecutionOutcome recorded"
    assert all(o.success for o in app.kernel._outcomes)

    # 3) procedural memory learned the 'exec:file' capability (reuse keyed by action)
    proc = app.procedural._procedures.get("exec:file")
    assert proc is not None and proc["runs"] >= 1, proc

    # 4) persist + cold boot -> experience restored
    app._save_knowledge()
    app2 = _make_app(tmp_path, snap)
    restored = app2.procedural._procedures.get("exec:file")
    assert restored is not None and restored["runs"] >= 1, restored

    # 5) repeating the goal grows the accumulated experience (reuse after restart)
    before = restored["runs"]
    app2.step("запиши hello в x.txt")
    after = app2.procedural._procedures["exec:file"]["runs"]
    assert after > before, (before, after)


def test_autonomous_command_goal_executes_and_learns(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # PUBLIC entry point, NO manual plan / execution_steps injection
    app.step("выполни echo hello")

    # 1) the REAL command ran — kernel recorded a successful outcome
    assert app.kernel._outcomes, "no ExecutionOutcome recorded"
    assert all(o.success for o in app.kernel._outcomes)

    # 2) procedural memory learned the 'exec:command' capability (reuse keyed by action)
    proc = app.procedural._procedures.get("exec:command")
    assert proc is not None and proc["runs"] >= 1, proc

    # 3) persist + cold boot -> experience restored
    app._save_knowledge()
    app2 = _make_app(tmp_path, snap)
    restored = app2.procedural._procedures.get("exec:command")
    assert restored is not None and restored["runs"] >= 1, restored

    # 4) repeating the goal grows the accumulated experience (reuse after restart)
    before = restored["runs"]
    app2.step("выполни echo hello")
    after = app2.procedural._procedures["exec:command"]["runs"]
    assert after > before, (before, after)


def test_intent_grammar_case_insensitive_and_negative():
    """Slice 3-alt hardening: case-insensitive split + negative goals emit no intent."""
    from kernel.planning import ReferencePlanner
    from contracts.cognitive_domain import Goal, ConfidenceScore, Provenance
    from contracts.i_world_model import WorldState

    p = ReferencePlanner(clock=None)

    # case-insensitive: capital 'В' still splits path/content
    g_ci = Goal(id="g", intent_id="i1", description="Запиши Hello В x.txt",
                confidence=ConfidenceScore(0.8), provenance=Provenance(source="intent", actor="kernel"))
    assert p.plan(g_ci, [], WorldState(node_id="n1"), 100)[0].execution_steps == (
        {"kind": "file", "path": "x.txt", "content": "Hello"},)

    # negative: no file/command keyword -> no structured intent
    for desc in ("расскажи про архитектуру KROFT", "сохрани спокойствие"):
        g = Goal(id="g", intent_id="i1", description=desc,
                 confidence=ConfidenceScore(0.8), provenance=Provenance(source="intent", actor="kernel"))
        assert p.plan(g, [], WorldState(node_id="n1"), 100)[0].execution_steps is None, desc


def test_negative_goal_creates_no_file(tmp_path):
    """A non-action goal must NOT produce a real file on disk via the public step()."""
    import os as _os
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    app.step("расскажи про архитектуру KROFT")

    # no real file action happened (only the snapshot + vault note may exist)
    created = [f.name for f in tmp_path.iterdir() if f.is_file() and f != snap]
    assert not any(f.endswith(".txt") for f in created), created
    assert app.kernel._outcomes  # loop still ran, just no structured action
