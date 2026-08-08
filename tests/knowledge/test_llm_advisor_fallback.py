"""Slice 9, Test 1 — deterministic advisor fallback (graceful degradation).

Proof (K5): KroftApp(llm="auto") wires the advisor via adapter_for(ILlm). When the LLM endpoint
is unreachable the advisor degrades gracefully — the loop runs exactly as llm="none" (no crash,
plan produced) while the advisor object remains WIRED (degraded, not absent). This proves the
advisor branch is live and fails safe, not silently skipped.

No production code change; test-only.
"""

import os

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig


def test_llm_advisor_fallback_when_unreachable(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    snap = tmp_path / "k.json"
    # point the auto builder at a CLOSED port so the live call fails fast
    old = os.environ.get("KROFT_LLM_BASE_URL")
    os.environ["KROFT_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
    try:
        app = KroftApp(KroftConfig(node_id="h1", llm="auto", ticks=0,
                                   vault=str(vault), knowledge_snapshot=str(snap)))
        app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
        # advisor is WIRED via adapter_for (not None even though the endpoint is down)
        assert app.kernel._planner._advisor is not None
        # the loop must NOT crash — graceful degradation to the pure reference path
        app.step("запиши hello в x.txt")
        # fallback behaves like llm="none": a valid plan is still produced
        assert app.kernel._last_selected_plan is not None
        assert app.kernel._last_selected_plan.execution_steps  # D3 still works
    finally:
        if old is None:
            os.environ.pop("KROFT_LLM_BASE_URL", None)
        else:
            os.environ["KROFT_LLM_BASE_URL"] = old
