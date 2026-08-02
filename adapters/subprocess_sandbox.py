"""Subprocess-based execution sandbox (TZ-EXECUTION-001, ADR-039).

K8-compliant: lives in adapters/ (infra). Imports ONLY contracts + stdlib.
No kernel/runtime/services imports. Thread-safe; UUID handles; timeout+kill.
Stdlib-only — zero external dependencies.
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from typing import Dict, List, Optional

from contracts.i_execution_sandbox import ExecutionResult, IExecutionSandbox

# Sensitive env vars stripped before passing to a sandboxed child process.
_ENV_DENY_LIST = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "HERMES_TOKEN",
    "KROFT_SECRET",
)


class SubprocessSandbox(IExecutionSandbox):
    """Stdlib subprocess sandbox. Command is a List[str] (no shell injection)."""

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._default_timeout = default_timeout
        self._lock = threading.Lock()
        self._procs: Dict[str, subprocess.Popen] = {}

    def execute(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout_sec: Optional[float] = None,
        cwd: Optional[str] = None,
        label: str = "",
    ) -> ExecutionResult:
        handle = str(uuid.uuid4())
        timeout = timeout_sec or self._default_timeout
        start = time.monotonic()

        child_env = self._sanitize_env(env)
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_env,
                cwd=cwd,
                text=True,
            )
        except (FileNotFoundError, OSError) as exc:
            duration_ms = (time.monotonic() - start) * 1000
            return ExecutionResult(
                returncode=127,
                stdout="",
                stderr=f"sandbox: failed to start: {exc}",
                handle=handle,
                duration_ms=duration_ms,
                killed=False,
            )

        with self._lock:
            self._procs[handle] = proc

        killed = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._terminate(proc)
            # communicate() already closed the pipes on timeout; do not re-read.
            stdout, stderr = "", ""
            killed = True
        finally:
            with self._lock:
                self._procs.pop(handle, None)

        duration_ms = (time.monotonic() - start) * 1000
        return ExecutionResult(
            returncode=-9 if killed else (proc.returncode or 0),
            stdout=stdout or "",
            stderr=stderr or "",
            handle=handle,
            duration_ms=duration_ms,
            killed=killed,
        )

    def kill(self, handle: str) -> bool:
        with self._lock:
            proc = self._procs.get(handle)
            if proc is None:
                return False
            self._terminate(proc)
        return True

    def health(self) -> bool:
        return True

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        except Exception:
            pass

    @staticmethod
    def _sanitize_env(env: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if env is None:
            return None
        return {k: v for k, v in env.items() if k not in _ENV_DENY_LIST}
