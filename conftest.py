"""Pytest bootstrap: ensure project root + first-party packages import cleanly.

The eager imports below guarantee that `contracts`, `kernel`, `runtime`,
`infrastructure`, `services`, `adapters` are fully registered in sys.modules
*before* pytest collects test modules. Without this, full-suite collection hits a
namespace-package conflict (ModuleNotFoundError on existing files such as
contracts.i_execution_sandbox / runtime.supervisor.circuit_breaker) because partial
package state leaks between collected test modules.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Eager registration of first-party top-level packages (bootstrap only).
for _pkg in ("contracts", "kernel", "runtime", "infrastructure", "services", "adapters"):
    try:
        __import__(_pkg)
    except Exception:
        # A package may be partially importable in isolation; let individual
        # tests surface real import errors rather than failing collection.
        pass
