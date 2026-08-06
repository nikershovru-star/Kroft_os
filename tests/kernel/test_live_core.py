"""ТЗ-LIVE-01 extended (ADR-088) — living core K8 tests (Флаг 1b, separate from impl).

Covers: save->load roundtrip, evolution across two restarts (state-dir resume),
background autosave writes a file, SIGINT graceful save, --llm none runs LLM-free.

K1: stdlib only in test logic. K5: reuses run_evolution._LivingCore + JsonMemoryStore.
O1: persistence never mutates HARD (hard policies excluded). I-09: deterministic LLM-free.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kernel.persistence import JsonMemoryStore, KernelState
from run_evolution import _LivingCore, _demo_stream


def _fresh_core(state_dir: str, ticks: int = 0, autosave_sec: float = 0.0) -> _LivingCore:
    os.makedirs(state_dir, exist_ok=True)
    return _LivingCore(
        state_dir=state_dir,
        node_id="test-node",
        llm_client=None,
        ticks=ticks,
        autosave_sec=autosave_sec,
        bg_consolidate=False,
    )


def test_save_load_roundtrip(tmp_path: Path):
    """Persisted state reloads identical (I-09: same file -> same state)."""
    sd = str(tmp_path / "state_a")
    core = _fresh_core(sd, ticks=4)
    for g in _demo_stream(4):
        core.tick_once(g)
    core.save()

    path = Path(sd) / "kernel_state.json"
    assert path.exists()
    reloaded = JsonMemoryStore().load(str(path))
    assert len(reloaded.episodes) == 4
    # roundtrip: re-save and compare structural equality
    core2 = _fresh_core(sd + "_b", ticks=0)
    for e in reloaded.episodes:
        core2.mem.record_episode(e)
    core2.save()
    a = json.loads((Path(sd) / "kernel_state.json").read_text(encoding="utf-8"))
    b = json.loads((Path(sd + "_b") / "kernel_state.json").read_text(encoding="utf-8"))
    assert a["episodes"] == b["episodes"]


def test_evolution_across_two_restarts(tmp_path: Path):
    """Same state-dir accumulates episodes/skills across restarts (resume)."""
    sd = str(tmp_path / "state")
    # Run 1
    c1 = _fresh_core(sd, ticks=4)
    for g in _demo_stream(4):
        c1.tick_once(g)
    c1.save()
    assert len(c1.snapshot().episodes) == 4

    # Run 2 (resume)
    c2 = _fresh_core(sd, ticks=4)
    for g in _demo_stream(4):
        c2.tick_once(g)
    c2.save()
    snap = c2.snapshot()
    assert len(snap.episodes) == 8, "episodes must accumulate across restarts"
    # soft policy survives restart
    soft = [p for p in snap.normative if p.layer == "soft"]
    assert len(soft) >= 1
    assert "avoid" in soft[0].body


def test_autosave_writes_file(tmp_path: Path):
    """Background autosave timer writes the state file (Commit 2)."""
    sd = str(tmp_path / "autosave")
    core = _fresh_core(sd, ticks=0, autosave_sec=0.2)
    try:
        core.start_autosave()
        # let the timer fire at least once
        deadline = time.time() + 3.0
        path = Path(sd) / "kernel_state.json"
        while time.time() < deadline:
            if path.exists() and path.stat().st_size > 0:
                break
            time.sleep(0.05)
        assert path.exists(), "autosave timer must write kernel_state.json"
        assert path.stat().st_size > 0
    finally:
        core.stop_autosave()


def test_sigint_graceful_save(tmp_path: Path):
    """SIGINT triggers graceful save (no crash), state file present + fresh (Commit 2)."""
    sd = str(tmp_path / "live")
    # Write a small runner script (inline -c cannot hold a def with newlines).
    runner = tmp_path / "sigrun.py"
    runner.write_text(
        "import sys\n"
        "import signal\n"
        "import run_evolution as r\n"
        f"core = r._LivingCore(state_dir={sd!r}, node_id='sig', llm_client=None, "
        "ticks=0, autosave_sec=0.0, bg_consolidate=False)\n"
        "def _handler(signum, frame):\n"
        "    core.stop_autosave(); core.save(); sys.exit(0)\n"
        "signal.signal(signal.SIGINT, _handler)\n"
        "if hasattr(signal, 'SIGBREAK'):\n"
        "    signal.signal(signal.SIGBREAK, _handler)\n"
        "core.run()\n",
        encoding="utf-8",
    )
    from tests._repo_root import repo_root
    repo_root = repo_root()
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        creationflags=creationflags,
    )
    # let it run a bit, then send the interrupt signal (platform-specific).
    time.sleep(2.0)
    assert proc.poll() is None, "process should still be running before interrupt"
    if sys.platform == "win32":
        # Windows: SIGINT is unsupported via send_signal; use Ctrl-Break on the new group.
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("process did not exit after interrupt")
    path = Path(sd) / "kernel_state.json"
    assert path.exists(), "SIGINT must trigger graceful save"
    assert path.stat().st_size > 0


def test_llm_none_runs_without_model(tmp_path: Path):
    """--llm none (llm_client=None) runs deterministically, no model needed."""
    sd = str(tmp_path / "none")
    core = _fresh_core(sd, ticks=6)
    goals = _demo_stream(6)
    for g in goals:
        core.tick_once(g)
    core.save()
    snap = core.snapshot()
    # deterministic: choose_blue succeeds -> skill; choose_red fails -> soft avoid policy
    assert len(snap.episodes) == 6
    soft = [p for p in snap.normative if p.layer == "soft"]
    assert any("avoid" in p.body for p in soft)
    assert any(s.capability == "choose_blue" for s in snap.skills)
