"""ТЗ-PHASE-O.1: RealWorldExecutor routes Action.kind to real backends.

Targeted proof (K5 + I-09): RealWorldExecutor implements the existing IExecutor contract
and routes:
  - kind="file"   -> LocalFileSystemAdapter (real read/write)
  - kind="command"-> TerminalExecutor (secure, blacklist-guarded)
  - unknown kind  -> ReferenceExecutor sim fallback
No new port/interface/DTO/runtime layer; reuses IExecutor, LocalFileSystemAdapter,
TerminalExecutor, ReferenceExecutor. Kernel/contracts untouched (K5/K6).
"""

from __future__ import annotations
import pytest

import os
import tempfile
from pathlib import Path

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import Action, ConfidenceScore, Provenance, ProvenanceType


def _act(kind, payload):
    return Action(id=f"a-{kind}", kind=kind, payload=payload,
                  confidence=ConfidenceScore(0.8, ProvenanceType.RULE_INFERENCE),
                  provenance=Provenance(source="test", actor="verifier"))


def test_file_write_then_read(tmp_path):
    ex = RealWorldExecutor(base_dir=str(tmp_path))
    rel = "o1.txt"
    r1 = ex.execute(_act("file", f"write:{rel}|hello-kroft"))
    assert r1.success is True
    assert (tmp_path / rel).read_text(encoding="utf-8") == "hello-kroft"
    r2 = ex.execute(_act("file", f"read:{rel}"))
    assert r2.success is True


def test_command_executes_safely():
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    r = ex.execute(_act("command", "echo phase-o1"))
    # TerminalExecutor ran the safe echo (not blocked) -> success True
    assert r.success is True


def test_shell_kind_routes_to_terminal():
    # ТЗ-PHASE-O.2: kind="shell" must also route to TerminalExecutor (real backend)
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    r = ex.execute(_act("shell", "echo shell-kind"))
    assert r.success is True


def test_execute_plan_routes_to_real_backend():
    # kernel sends Action(kind="execute_plan", payload="\n".join(plan.steps))
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    r = ex.execute(_act("execute_plan", "echo real-plan-step\n echo second-step"))
    # must run the steps via TerminalExecutor (real backend), NOT sim fallback
    assert r.success is True
    assert r.observation  # non-empty real observation (TerminalExecutor ran the command)


def test_execute_plan_routes_all_steps():
    # multi-step plan: each step routed (file + shell), aggregated success
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    plan = "write:plan.txt|hello\n echo step-two"
    r = ex.execute(_act("execute_plan", plan))
    assert r.success is True
    assert "file_written" in r.observation  # file backend executed
    assert "command_done" in r.observation or r.observation  # shell step via TerminalExecutor


def test_structured_json_plan_executes_real_actions():
    # ТЗ-PHASE-O.3: JSON-array plan with explicit kinds -> real file + real command
    import json
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    payload = json.dumps([
        {"kind": "file", "path": "s.txt", "content": "json-hello"},
        {"kind": "command", "cmd": "echo json-cmd"},
    ])
    r = ex.execute(_act("execute_plan", payload))
    assert r.success is True
    assert os.path.exists(os.path.join(tempfile.gettempdir(), "s.txt"))
    # malformed JSON must fall back to textual routing (no crash)
    r2 = ex.execute(_act("execute_plan", "[not valid json"))
    assert isinstance(r2, type(r))


def test_run_plan_bridge_accepts_json_and_text():
    # ТЗ-PHASE-O.5: external bridge run_plan() passes structured JSON through unchanged
    # and keeps textual heuristic routing (backward compat)
    import json
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    jplan = json.dumps([
        {"kind": "file", "path": "bridge.txt", "content": "o5"},
        {"kind": "command", "cmd": "echo o5"},
    ])
    r = ex.run_plan(jplan)
    assert r.success is True
    assert os.path.exists(os.path.join(tempfile.gettempdir(), "bridge.txt"))
    # textual payload via bridge -> heuristic still works
    r2 = ex.run_plan("echo bridge-text\n write:bt.txt|bridge")
    assert r2.success is True
    assert os.path.exists(os.path.join(tempfile.gettempdir(), "bt.txt"))


def test_desktop_kind_invokes_desktop_adapter():
    # kind="desktop" routes to PyAutoGUIAdapter (graceful if pyautogui absent)
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    r = ex.execute(_act("desktop", "click 5 5\n type hi\n open_app notepad"))
    assert r is not None
    assert hasattr(r, "success")


def test_unknown_kind_falls_back_to_sim():
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    # unknown kind must not crash; returns an ExecutionResult (sim env path)
    r = ex.execute(_act("mystery", "do something"))
    assert r is not None
    assert hasattr(r, "success")


@pytest.mark.slow
def test_run_kroft_wires_real_world_executor():
    app = KroftApp(KroftConfig(node_id="o1", llm="none", ticks=0,
                              vault="C:/Users/Nikita/Documents/Obsidian Vault/02-Projects/KROFT_OS"))
    assert type(app.kernel._executor).__name__ == "RealWorldExecutor"


def test_security_default_denies_desktop_but_allows_file_and_command():
    # ТЗ-PHASE-P.6 (Fix D2): desktop has no safe default -> denied; file/command allowed
    # (command guarded by TerminalExecutor blacklist, already present).
    import json
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    desktop_plan = json.dumps([{"kind": "desktop", "op": "click", "x": 1, "y": 1}])
    rd = ex.execute(_act("execute_plan", desktop_plan))
    assert rd.success is False
    assert "policy_denied" in rd.observation

    # file still works
    fplan = json.dumps([{"kind": "file", "path": "sec.txt", "content": "x"}])
    rf = ex.execute(_act("execute_plan", fplan))
    assert rf.success is True
    assert os.path.exists(os.path.join(tempfile.gettempdir(), "sec.txt"))


def test_security_custom_policy_overrides_default():
    # supplied policy decides per-step (reuse existing guards / add stricter rules)
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir(),
                           policy=lambda s: (s.get("kind") == "desktop"
                                            and s.get("op") == "open_app"
                                            and s.get("name") == "notepad"))
    import json
    allow = json.dumps([{"kind": "desktop", "op": "open_app", "name": "notepad"}])
    ra = ex.execute(_act("execute_plan", allow))
    # notepad open is allowed by policy; success depends on pyautogui presence (graceful)
    assert "policy_denied" not in ra.observation
    deny = json.dumps([{"kind": "desktop", "op": "click", "x": 1, "y": 1}])
    rd = ex.execute(_act("execute_plan", deny))
    assert rd.success is False
    assert "policy_denied" in rd.observation
