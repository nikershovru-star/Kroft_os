"""Real-World Executor Adapter (ТЗ-PHASE-O.1).

Minimal IExecutor that routes an Action to REAL execution backends, reusing existing
components (K5) and touching NO kernel/contracts code (K6):

  Action.kind == "file"         -> LocalFileSystemAdapter (read/write)   [adapters/filesystem_adapter.py]
  Action.kind == "command"      -> SubprocessSandbox (List[str], kill-on-timeout) [adapters/subprocess_sandbox.py]
  Action.kind == "execute_plan" -> SubprocessSandbox (real plan steps executed by the OS)
  unknown kind                  -> ReferenceExecutor / ReferenceExecutionEnvironment (sim fallback)

Lives in composition/ (the composition root) because it wires adapters together;
adapters/ is forbidden from importing services/ by the arch-gate (K6/V3), so the
cross-layer join belongs here. Implements the existing IExecutor contract; no new
port/interface/DTO/runtime layer. Wired from run_kroft via CognitiveKernel.attach_executor
(ТЗ-EX-01 / PHASE N).
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from contracts.cognitive_domain import (
    Action, CausalMark, ConfidenceScore, NodeLamportClock, ProvenanceType,
)
from contracts.i_execution import ExecutionResult, IExecutor
from kernel.execution import ReferenceExecutor, ReferenceExecutionEnvironment


class RealWorldExecutor(IExecutor):
    """Routes Action.kind to a real backend; unknown kinds fall back to the sim env.

    File operations are confined to ``base_dir`` (LocalFileSystemAdapter sandbox); when
    None, a temp dir is used so the real backend is exercised safely by default.
    """

    def __init__(self, clock: Optional[NodeLamportClock] = None,
                 base_dir: Optional[str] = None) -> None:
        self._base_dir = base_dir or tempfile.gettempdir()
        self._fs = None
        self._sandbox = None
        self._sim = ReferenceExecutor(environment=ReferenceExecutionEnvironment(clock), clock=clock)

    # --- backend accessors (lazy, keep imports localized) -------------------
    def _filesystem(self):
        if self._fs is None:
            from adapters.filesystem_adapter import LocalFileSystemAdapter
            self._fs = LocalFileSystemAdapter(self._base_dir)
        return self._fs

    def _get_sandbox(self):
        if self._sandbox is None:
            from adapters.subprocess_sandbox import SubprocessSandbox
            self._sandbox = SubprocessSandbox(default_timeout=30.0)
        return self._sandbox

    # --- IExecutor ---------------------------------------------------------
    def execute(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        kind = (action.kind or "").lower()
        if kind == "file":
            return self._exec_file(action)
        if kind in ("command", "execute_plan"):
            return self._exec_command(action, timeout)
        # unknown kind -> deterministic simulation (backward compatible)
        return self._sim.execute(action, timeout)

    # --- backends ----------------------------------------------------------
    def _exec_file(self, action: Action) -> ExecutionResult:
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        payload = action.payload or ""
        try:
            if payload.startswith("write:"):
                _, rest = payload.split("write:", 1)
                path, _, content = rest.partition("|")
                ok = self._filesystem().write_content(path.strip(), content)
                return ExecutionResult(
                    action_id=action.id, success=bool(ok),
                    observation=f"file_written:{path}" if ok else "file_write_failed",
                    reward=0.9 if ok else 0.0, confidence=conf, causal=mark)
            if payload.startswith("read:"):
                path = payload.split("read:", 1)[1].strip()
                data = self._filesystem().read_content(path)
                return ExecutionResult(
                    action_id=action.id, success=True,
                    observation=f"file_read:{len(data)} bytes", reward=0.9,
                    confidence=conf, causal=mark)
            return ExecutionResult(
                action_id=action.id, success=False,
                observation="file: unknown op (use write:path|content or read:path)",
                reward=0.0, confidence=conf, causal=mark)
        except Exception as exc:  # noqa: BLE001 — real backend errors must not crash the loop
            return ExecutionResult(
                action_id=action.id, success=False,
                observation=f"file_error:{exc}", reward=0.0, confidence=conf, causal=mark)

    def _exec_command(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        """Route to SubprocessSandbox (real OS execution, List[str], kill-on-timeout).

        For 'execute_plan' the kernel passes payload="\\n".join(plan.steps); the first
        step is executed as a real command so the cognitive loop records a REAL outcome
        (not the proxy). For 'command' the payload is the command string.
        """
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        try:
            payload = (action.payload or "").strip()
            # first non-empty line = the command to run
            cmd_line = next((ln.strip() for ln in payload.splitlines() if ln.strip()), "")
            if not cmd_line:
                cmd_line = "echo ok"
            command = cmd_line.split()
            result = self._get_sandbox().execute(
                command, timeout_sec=timeout or 30.0, cwd=self._base_dir)
            # SubprocessSandbox returns contracts.i_execution_sandbox.ExecutionResult
            # (returncode/stdout/stderr/killed) -> map to IExecutor ExecutionResult.
            rc = getattr(result, "returncode", -1)
            killed = bool(getattr(result, "killed", False))
            success = (rc == 0) and not killed
            out = (getattr(result, "stdout", "") or getattr(result, "stderr", "") or "").strip()
            return ExecutionResult(
                action_id=action.id,
                success=success,
                observation=out[:200] or ("killed" if killed else "command_done"),
                reward=0.9 if success else 0.1,
                confidence=conf,
                causal=mark,
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                action_id=action.id, success=False,
                observation=f"command_error:{exc}", reward=0.0, confidence=conf, causal=mark)
