"""Slice: desktop opt-in policy (P.6) — default-deny, explicit opt-in only.

Proof (K5): screen automation (click/type/open_app) is blocked by default and
only runs when the operator explicitly opts in — via env ``KROFT_DESKTOP_OPT_IN=1``
OR ``KroftConfig.desktop_opt_in``. Reuses the existing RealWorldExecutor chokepoint
(``_route_desktop_step``) and the no-op ``MockDesktopAdapter`` for deterministic
execution. No real GUI is touched in CI; the live PyAutoGUIAdapter path is gated
on ``DESKTOP_LIVE=1`` (skipped otherwise).

No new port/DTO/layer; planner emits NO desktop intent (only explicit markers
click:/type:/open: are routed). Default-deny preserved end-to-end.
"""

import os

from contracts.cognitive_domain import (
    Action, ConfidenceScore, Provenance, ProvenanceType,
)
from composition.real_world_executor import RealWorldExecutor
from adapters.desktop_adapter import MockDesktopAdapter


def _make_exec(opt_in: bool) -> RealWorldExecutor:
    ex = RealWorldExecutor(desktop_opt_in=opt_in)
    # deterministic backend (no real GUI); mock still exercises the opt-in gate
    ex._desktop = MockDesktopAdapter()
    return ex


def test_default_deny_blocks_desktop():
    """Without opt-in, every desktop path is denied (policy_denied:desktop)."""
    ex = _make_exec(opt_in=False)

    # direct Action(kind="desktop")
    r = ex.execute(Action(id="a1", kind="desktop", payload="click 10 20",
                          confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                          provenance=Provenance(source="t", actor="t")))
    assert not r.success and r.observation == "policy_denied:desktop", r.observation

    # structured plan with a desktop step
    import json
    plan = json.dumps([{"kind": "desktop", "op": "type", "text": "hi"}])
    r2 = ex.execute(Action(id="a2", kind="execute_plan", payload=plan,
                           confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                           provenance=Provenance(source="t", actor="t")))
    assert not r2.success and "policy_denied" in r2.observation, r2.observation

    # textual plan with a desktop line
    r3 = ex.execute(Action(id="a3", kind="execute_plan", payload="type hello world",
                           confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                           provenance=Provenance(source="t", actor="t")))
    assert not r3.success and "policy_denied" in r3.observation, r3.observation


def test_opt_in_executes_via_mock():
    """With opt-in, desktop steps execute through the (mock) adapter."""
    ex = _make_exec(opt_in=True)

    r = ex.execute(Action(id="b1", kind="desktop", payload="click 10 20",
                          confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                          provenance=Provenance(source="t", actor="t")))
    assert r.success and r.observation == "desktop_click:10,20", r.observation

    # textual desktop line
    r2 = ex.execute(Action(id="b2", kind="execute_plan", payload="open_app notepad",
                           confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                           provenance=Provenance(source="t", actor="t")))
    assert r2.success and "desktop_open:notepad" in r2.observation, r2.observation

    # structured desktop step
    import json
    plan = json.dumps([{"kind": "desktop", "op": "type", "text": "hi"}])
    r3 = ex.execute(Action(id="b3", kind="execute_plan", payload=plan,
                           confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                           provenance=Provenance(source="t", actor="t")))
    assert r3.success and "desktop_type:2 chars" in r3.observation, r3.observation


def test_env_var_opt_in():
    """Env KROFT_DESKTOP_OPT_IN=1 enables desktop even with default KroftConfig."""
    old = os.environ.get("KROFT_DESKTOP_OPT_IN")
    os.environ["KROFT_DESKTOP_OPT_IN"] = "1"
    try:
        ex = RealWorldExecutor()
        ex._desktop = MockDesktopAdapter()
        # bypass attach path: simulate what KroftApp wiring does via env
        assert ex._desktop_opt_in is False  # constructor default
        # the real resolution happens in KroftApp; emulate it:
        from composition.run_kroft import KroftConfig, KroftApp
        import tempfile
        snap = os.path.join(tempfile.mkdtemp(), "k.json")
        app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                                   vault=os.path.join(tempfile.mkdtemp(), "v"),
                                   knowledge_snapshot=snap))
        assert app.kernel._executor._desktop_opt_in is True, "env opt-in must reach executor"
        # deterministic backend (no real GUI in CI)
        app.kernel._executor._desktop = MockDesktopAdapter()
        r = app.kernel._executor.execute(
            Action(id="e1", kind="desktop", payload="click 1 1",
                   confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                   provenance=Provenance(source="t", actor="t")))
        # mock adapter -> success; real GUI only with PyAutoGUIAdapter (not wired here)
        assert r.success, r.observation
    finally:
        if old is None:
            os.environ.pop("KROFT_DESKTOP_OPT_IN", None)
        else:
            os.environ["KROFT_DESKTOP_OPT_IN"] = old


def test_live_desktop_gated():
    """Real GUI automation: gated on DESKTOP_LIVE=1 AND a usable display.

    Safe by design (ТЗ option a): never touches the screen in CI. Skips when the
    flag is absent OR when PyAutoGUI / a display server is unavailable (headless CI).
    When both hold, proves the live PyAutoGUIAdapter path is wired and executes a
    desktop step through the opt-in-gated RealWorldExecutor without crashing.
    """
    import pytest
    if not os.environ.get("DESKTOP_LIVE"):
        pytest.skip("requires live desktop (DESKTOP_LIVE=1)")
    from adapters.desktop_adapter import PyAutoGUIAdapter
    adapter = PyAutoGUIAdapter()
    if not adapter.available():
        pytest.skip("no GUI/display available (PyAutoGUI or DISPLAY missing)")
    # proof the live path is alive: construct + execute one click through the executor
    ex = RealWorldExecutor(desktop_opt_in=True)
    ex._desktop = adapter
    r = ex.execute(Action(id="l1", kind="desktop", payload="click 0 0",
                          confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                          provenance=Provenance(source="t", actor="t")))
    assert r.observation.startswith("desktop_"), r.observation
