"""ProcessRegistry — registry of IProcess components (NOT concrete platforms).

Per Phase 2 (LAW K2): stores IProcess, never concrete platform classes. The Kernel
sees pid + status only. UUID-based pid (not OS PID). Depends ONLY on contracts
(arch-gate LAW K8). No wrapper files, no platform imports.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts import IProcess, IProcessRegistry, ProcessStatus


class ProcessRegistry(IProcessRegistry):
    """Maps component name -> IProcess. Kernel-facing registry."""

    def __init__(self) -> None:
        self._procs: Dict[str, IProcess] = {}

    def register(self, process: IProcess) -> None:
        self._procs[process.name] = process

    def get(self, name: str) -> Optional[IProcess]:
        return self._procs.get(name)

    def list(self) -> List[str]:
        return list(self._procs.keys())

    def kill(self, name: str) -> None:
        proc = self._procs.get(name)
        if proc is not None:
            proc.stop()

    def stop_all(self) -> None:
        """Graceful shutdown of every registered process (Kernel.stop path)."""
        for proc in self._procs.values():
            try:
                proc.stop()
            except Exception:
                pass
