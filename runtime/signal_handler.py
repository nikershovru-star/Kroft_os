"""Signal handlers — graceful shutdown + panic routing (Phase 4).

Thin integration over the IKernel contract (arch-gate: runtime.* -> contracts only).
Does NOT import the concrete kernel; receives an `IKernel` implementation via
injection. No XxxWrapper adapters, no second kernel.

Phase 4: SIGINT/SIGTERM escalate to the kernel's panic path (Level 3 — emergency
shutdown). If the kernel exposes `panic()`, we route there (snapshot + stop); else
fall back to `stop()`. The kernel itself decides what "panic" means (FSM -> FAILED
-> snapshot -> stop); the handler only triggers it.
"""
from __future__ import annotations

import os
import signal

from contracts import IKernel


def install_signal_handlers(kernel: IKernel) -> None:
    """Attach SIGINT/SIGTERM -> kernel panic/stop on an injected IKernel.

    Level 3 (kernel panic / emergency shutdown) is triggered on Ctrl-C / terminate.
    """
    def _panic():
        try:
            if hasattr(kernel, "panic"):
                kernel.panic("signal")
            else:
                kernel.stop()
        except Exception:
            pass

    if os.name == "nt":  # Windows Console Ctrl-C
        try:
            import ctypes
            kernel32 = ctypes.windll if hasattr(ctypes, "windll") else None
            if kernel32:
                def _handler(ctrl_type: int) -> int:
                    if ctrl_type == 0:  # CTRL_C_EVENT
                        _panic()
                    return 0
                kernel32.SetConsoleCtrlHandler(_handler, 1)
        except Exception:
            pass
    else:
        def _sig(_signum, _frame):
            _panic()
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
