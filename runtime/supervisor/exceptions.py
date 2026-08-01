"""Supervisor exceptions + Panic severity levels (Phase 4).

Per Phase 4 Panic Handler: three severity tiers so a single agent error cannot
take down the whole OS.
  Level 1 — Component exception  -> Supervisor.restart(component)
  Level 2 — Runtime exception    -> Snapshot + Recovery
  Level 3 — Kernel panic         -> Emergency shutdown

These are plain exceptions (stdlib) — no platform/adapters/plugins imports.
"""
from __future__ import annotations


class SupervisorError(Exception):
    """Base class for supervisor-layer errors."""


class ComponentFailure(SupervisorError):
    """Level 1: a component raised during its run-loop."""


class RuntimeFailure(SupervisorError):
    """Level 2: a runtime-layer (non-kernel) exception that needs snapshot+recovery."""


class KernelPanic(SupervisorError):
    """Level 3: unrecoverable kernel-level fault -> emergency shutdown."""


PANIC_LEVELS = {
    1: "component_exception -> Supervisor.restart(component)",
    2: "runtime_exception   -> Snapshot + Recovery",
    3: "kernel_panic        -> Emergency shutdown",
}
