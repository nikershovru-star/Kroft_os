"""Execution sandbox port (TZ-EXECUTION-001, ADR-039).

K1-compliant: stdlib only. Defines the isolated command-execution contract
that agents/tools use instead of calling os.system / subprocess directly.
The concrete impl (SubprocessSandbox) lives in adapters/ (K8).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of a sandboxed command execution."""

    returncode: int
    stdout: str
    stderr: str
    handle: str
    duration_ms: float
    killed: bool = False


class IExecutionSandbox(ABC):
    """Port for isolated command execution (TZ-EXECUTION-001, ADR-039)."""

    @abstractmethod
    def execute(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout_sec: Optional[float] = None,
        cwd: Optional[str] = None,
        label: str = "",
    ) -> ExecutionResult:
        """Run `command` (List[str], NOT a shell string) in isolation.

        Raises subprocess.TimeoutExpired indirectly handled by impl: on timeout
        the impl terminates/kills the process and returns ExecutionResult with
        killed=True, returncode=-9.
        """

    @abstractmethod
    def kill(self, handle: str) -> bool:
        """Terminate a running process by its handle. True if found."""

    @abstractmethod
    def health(self) -> bool:
        """Liveness check for the sandbox subsystem."""
