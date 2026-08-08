"""Slice 3-alt — episodic retrieval informs planning (reuse as CONTEXT).

Proof (K5): past Episodes are retrieved by keyword overlap with the goal and
injected into the plan as a 'past-experience:' step, so the loop reuses prior
experience — not just a runs counter. Episodes already persist + restore, so
retrieval works across restarts. Reuses InMemoryLayeredMemory + CognitiveKernel.tick
(public KroftApp.step). No new port/DTO/layer.
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


def test_episodic_retrieval_informs_planning(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    app = _make_app(tmp_path, snap)

    # --- first goal: no episode exists yet -> plan has NO past-experience reference
    app.step("запиши hello в x.txt")
    first_plan = app.kernel._last_selected_plan
    assert not any("past-experience" in s for s in first_plan.steps), first_plan.steps

    # the experience was recorded as an Episode
    eps = app.kernel._memory.get_episodes()
    assert eps, "no episode recorded after first goal"
    first_ep_summary = eps[0].summary

    # --- second, SIMILAR goal: planning should now reference the past episode
    app.step("запиши hello в x.txt")
    second_plan = app.kernel._last_selected_plan
    assert any(first_ep_summary in s for s in second_plan.steps), second_plan.steps

    # --- after cold boot (episodes restored) retrieval still works
    app._save_knowledge()
    app2 = _make_app(tmp_path, snap)
    assert app2.kernel._memory.get_episodes(), "episodes not restored after cold boot"
    app2.step("запиши hello в x.txt")
    reboot_plan = app2.kernel._last_selected_plan
    assert any(first_ep_summary in s for s in reboot_plan.steps), reboot_plan.steps
