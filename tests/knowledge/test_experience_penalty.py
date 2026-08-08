"""Slice 6 — experience penalty for low success-rate (proof).

Proof (K5): after accumulating FAILED executions of a capability, the planner lowers the
confidence of plans that carry that execution intent; after accumulating SUCCESSES it raises
them. Symmetrically biased around success_rate 0.5 (Slice 6 formula).

- Negative experience: real loop runs a command that fails (nonexistent binary -> exit!=0
  -> success=False). After 3+ failures on exec:command, a similar goal selects a plan with
  LOWER confidence than the same goal chosen before any experience existed.
- Positive control lives in test_live_experience_ranking (file success -> after > before);
  this file only adds the penalty direction. No new port/DTO/layer; kernel/planning only.
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


def test_experience_penalty_for_failures(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # BEFORE any experience: same-goal plan confidence (no success_rate bias yet)
    app.step("выполни nonexistent_binary_xyz_12345")
    before = app.kernel._last_selected_plan.confidence.value

    # build REAL failure experience through the real loop (command that exits != 0)
    for _ in range(3):
        app.step("выполни nonexistent_binary_xyz_12345")

    # AFTER failures: a (similar) command goal through the REAL loop — experience bias
    # must LOWER the selected plan's confidence below the pre-experience baseline.
    app.step("выполни another_missing_cmd_999")
    after = app.kernel._last_selected_plan.confidence.value

    assert after < before, (after, before)
