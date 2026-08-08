"""Slice 5 — live wiring: experience-informed ranking works in the REAL loop.

Proof (K5): after wiring, app.kernel._planner._procedural IS app.procedural (the real
procedural memory built from actual executed actions). Driving the loop with real file
actions (app.step) accumulates exec:file experience; a subsequent file goal selects a
plan whose confidence EXCEEDS the same-goal plan chosen BEFORE any experience existed
(isolates the experience bias — same loop, same goal family, only memory differs).
No manual planner injection — only KroftApp.step. Reuses InMemoryProceduralMemory.
"""

from __future__ import annotations

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig


def _make_app(tmp_path, snapshot):
    app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                               vault=str(tmp_path / "vault"),
                               knowledge_snapshot=str(snapshot)))
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    return app


def test_live_wiring_experience_ranking(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # wiring: planner holds the SAME procedural memory the app accumulates
    # (asserted after the first step so build_kernel has wired it)
    app.step("запиши hello в x.txt")
    assert app.kernel._planner._procedural is app.procedural

    # BEFORE any experience: same-goal plan confidence (no success_rate bias yet)
    before = app.kernel._last_selected_plan.confidence.value

    # build real exec:file experience through the real loop
    for _ in range(3):
        app.step("запиши hello в x.txt")

    # AFTER experience: a (similar) file goal through the REAL loop — experience bias
    # must raise the selected plan's confidence above the pre-experience baseline.
    app.step("запиши world в y.txt")
    after = app.kernel._last_selected_plan.confidence.value

    assert after > before, (after, before)
