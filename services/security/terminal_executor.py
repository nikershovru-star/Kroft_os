"""Secure Terminal Executor (TZ-SEC-001 WP-05).

Blacklist dangerous commands (rm -rf, shutdown, format, diskpart, reg delete,
del /f /s, taskkill *, sudo, powershell download, curl | bash). Whitelist mode
optional. Timeout enforced. On Windows, full OS sandbox is unavailable, so we
degrade gracefully: blacklist + timeout + (optional) job-object limits are the
only enforcement (seccomp/cgroups are Linux-only). R5 of TZ-SEC-001.
K1-compliant for services: contracts + stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import List, Optional

from contracts.security import ITerminalExecutor, TerminalResult

_BLACKLIST = [
    r"\brm\s+-rf\b", r"\brm\b.*--recursive.*--force", r"\bshutdown\b",
    r"\bformat\b", r"\bdiskpart\b", r"\breg\s+delete\b", r"\bdel\b\s+/[fs]",
    r"\btaskkill\b.*\*", r"\bsudo\b", r"powershell.*download",
    r"curl\b.*\|\s*bash", r"wget\b.*\|\s*bash", r"\bdd\b\s+if=",
]

# Allowed only in whitelist mode.
_DEFAULT_WHITELIST = [
    r"^(dir|ls|pwd|echo|cat|type|cd|git\s+status|git\s+log|git\s+diff|python\s+-c|pip\s+list)\b",
]


class TerminalExecutor(ITerminalExecutor):
    def __init__(self, blacklist: Optional[List[str]] = None,
                 whitelist: Optional[List[str]] = None,
                 default_timeout: float = 30.0,
                 enabled: bool = True) -> None:
        import re
        self._black = [re.compile(p, re.IGNORECASE) for p in (blacklist or _BLACKLIST)]
        self._white = [re.compile(p, re.IGNORECASE) for p in (whitelist or [])]
        self._timeout = default_timeout
        self._enabled = enabled

    def execute(self, command: str, timeout: float = 30.0) -> TerminalResult:
        if not self._enabled:
            return TerminalResult(0, "", "", blocked=True,
                                 block_reason="terminal disabled")
        # Blacklist check.
        for pat in self._black:
            if pat.search(command):
                return TerminalResult(0, "", "", blocked=True,
                                     block_reason=f"blocked by policy: {pat.pattern}")
        # Whitelist mode (if any whitelist patterns configured).
        if self._white and not any(p.search(command) for p in self._white):
            return TerminalResult(0, "", "", blocked=True,
                                  block_reason="not in whitelist")
        try:
            proc = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            try:
                out, err = proc.communicate(timeout=timeout or self._timeout)
                return TerminalResult(proc.returncode, out or "", err or "", blocked=False)
            except subprocess.TimeoutExpired:
                proc.kill()
                return TerminalResult(-1, "", "timeout", blocked=True,
                                      block_reason="execution timeout")
        except Exception as exc:  # noqa: BLE001
            return TerminalResult(-1, "", str(exc), blocked=False)
