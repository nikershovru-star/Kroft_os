"""Slice 7 — capstone end-to-end learning-journey proof (test-only).

One scenario driven entirely through the PUBLIC app.step API (no manual planner injection):
every link in the autonomous learning chain is asserted separately, with a comment on what
it proves. Reuses KroftApp + RealWorldExecutor + InMemoryProceduralMemory + layered memory;
no new port/DTO/layer (K5). Proves the full journey:
  D3 (NL-goal -> execution_steps) -> real action on disk -> single-write learning ->
  lean episode -> retrieval (past-experience) -> experience ranking (success boosts, failure
  penalizes) -> persistence (cold boot restores + keeps retrieval/ranking live).
"""

from __future__ import annotations

import os

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig


def _make_app(tmp_path, snapshot):
    app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                               vault=str(tmp_path / "vault"),
                               knowledge_snapshot=str(snapshot)))
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    return app


def test_capstone_learning_journey(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # --- BEFORE any experience: baseline file-goal confidence (no success_rate bias yet) ---
    app.step("запиши hello в x.txt")
    before_file = app.kernel._last_selected_plan.confidence.value

    # D3: NL goal produced a structured execution intent (no manual injection)
    plan0 = app.kernel._last_selected_plan
    assert plan0.execution_steps, "D3: NL goal must yield execution_steps"
    assert plan0.execution_steps[0]["kind"] == "file"

    # real action: the file is actually on disk with the requested content
    target = tmp_path / "x.txt"
    assert target.exists(), "real action: file must exist on disk"
    assert target.read_text(encoding="utf-8") == "hello", "real action: content written"

    # --- accumulate file experience (single-write) ---
    for _ in range(2):  # +2 -> total 3 runs
        app.step("запиши hello в x.txt")

    # single-write learning: exactly 3 runs, all successful -> success_rate 1.0
    rec = app.procedural._procedures["exec:file"]
    assert rec["runs"] == 3, rec
    assert rec["successes"] == 3, rec
    assert rec["success_rate"] == 1.0, rec

    # lean episode: summary carries structured intent, NOT the file content
    eps = app.kernel._memory.get_episodes()
    assert eps, "episode must be recorded"
    summary = eps[0].summary
    assert "exec:file:x.txt" in summary, summary
    assert "hello" not in summary, summary  # lean: content not embedded

    # --- retrieval: a similar goal references the past episode ---
    app.step("запиши world в y.txt")
    similar_plan = app.kernel._last_selected_plan
    assert any("past-experience" in s for s in similar_plan.steps), similar_plan.steps
    assert any(summary in s for s in similar_plan.steps), similar_plan.steps

    # --- ranking (success): confidence after experience > before any experience ---
    app.step("запиши data в z.txt")  # similar goal, experience present
    after_file = app.kernel._last_selected_plan.confidence.value
    assert after_file > before_file, (after_file, before_file)

    # --- BEFORE any command experience: baseline command-goal confidence ---
    app.step("выполни nonexistent_binary_xyz_12345")
    before_fail = app.kernel._last_selected_plan.confidence.value

    # --- accumulate command failures (single-write, all failures) ---
    for _ in range(3):  # total 4 runs for exec:command; first already above
        app.step("выполни nonexistent_binary_xyz_12345")

    # single-write learning for the failing capability
    rec_cmd = app.procedural._procedures["exec:command"]
    assert rec_cmd["runs"] == 4, rec_cmd
    assert rec_cmd["successes"] == 0, rec_cmd
    assert rec_cmd["success_rate"] == 0.0, rec_cmd

    # --- ranking (failure): a failing capability is penalized ---
    app.step("выполни another_missing_cmd_999")  # similar goal, failures present
    after_fail = app.kernel._last_selected_plan.confidence.value
    assert after_fail < before_fail, (after_fail, before_fail)

    # --- persistence: cold boot restores procedural + episodic state ---
    expected_file_runs = app.procedural._procedures["exec:file"]["runs"]
    app._save_knowledge()
    app2 = _make_app(tmp_path, snap)
    # procedural runs restored (exact, not reset)
    assert app2.procedural._procedures["exec:file"]["runs"] == expected_file_runs
    # episodic summary restored (lean form)
    eps2 = app2.kernel._memory.get_episodes()
    assert eps2 and "exec:file:x.txt" in eps2[0].summary

    # after restart: retrieval still active
    app2.step("запиши another в w.txt")
    assert any("past-experience" in s for s in app2.kernel._last_selected_plan.steps)
    # after restart: ranking still active — the LOADED experience boosts confidence
    # above the pre-experience baseline captured at the very start (before_file).
    app2.step("запиши new в q.txt")
    conf_with_exp = app2.kernel._last_selected_plan.confidence.value
    assert conf_with_exp > before_file, (conf_with_exp, before_file)
