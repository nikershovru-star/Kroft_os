"""Signal handlers — graceful shutdown on SIGINT/SIGTERM.

Thin integration over the IKernel contract (arch-gate: runtime.* -> contracts only).
Does NOT import the concrete kernel; receives an `IKernel` implementation via
injection. No XxxWrapper adapters, no second kernel.
"""
from __future__ import annotations

import os
import signal

from contracts import IKernel


def install_signal_handlers(kernel: IKernel) -> None:
    """Attach SIGINT/SIGTERM -> graceful stop on an injected IKernel."""
    if os.name == "nt":  # Windows Console Ctrl-C
        try:
            import ctypes
            kernel32 = ctypes.windll if hasattr(ctypes, "windll") else None
            if kernel32:
                def _handler(ctrl_type: int) -> int:
                    if ctrl_type == 0:  # CTRL_C_EVENT
                        try:
                            kernel.stop()
                        except Exception:
                            pass
                    return 0
                kernel32.SetConsoleCtrlHandler(_handler, 1)
        except Exception:
            pass
    else:
        def _sig(_signum, _frame):
            try:
                kernel.stop()
            except Exception:
                pass
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
