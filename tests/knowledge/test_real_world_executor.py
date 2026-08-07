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


def test_execute_plan_routes_to_real_backend():
    # kernel sends Action(kind="execute_plan", payload="\n".join(plan.steps))
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    r = ex.execute(_act("execute_plan", "echo real-plan-step\nsecond step"))
    # must run the first step via SubprocessSandbox, NOT sim fallback
    assert r.success is True
    assert "real-plan-step" in r.observation


def test_unknown_kind_falls_back_to_sim():
    ex = RealWorldExecutor(base_dir=tempfile.gettempdir())
    # unknown kind must not crash; returns an ExecutionResult (sim env path)
    r = ex.execute(_act("mystery", "do something"))
    assert r is not None
    assert hasattr(r, "success")


def test_run_kroft_wires_real_world_executor():
    app = KroftApp(KroftConfig(node_id="o1", llm="none", ticks=0,
                              vault="C:/Users/Nikita/Documents/Obsidian Vault/02-Projects/KROFT_OS"))
    assert type(app.kernel._executor).__name__ == "RealWorldExecutor"
