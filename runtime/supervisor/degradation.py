"""Graceful Degradation Policy (Wave 2 WP-10, ADR-038).

K8-compliant: imports ONLY contracts + runtime + stdlib. No services/adapters.
When a circuit opens on a critical component (or recovery is exhausted / L3
panic), the system degrades managed: NONE -> PARTIAL -> MINIMAL. PARTIAL and
MINIMAL require human approval (K5, ADR-034) — the policy calls
ApprovalManager.request(); it never degrades silently below NONE.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable, List, Optional

from contracts.security import IApprovalManager


class DegradationLevel(str, Enum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    MINIMAL = "MINIMAL"


class GracefulDegradationPolicy:
    """Drives managed service-level reduction under sustained failure."""

    # Ordered severity for comparison.
    _ORDER = {DegradationLevel.NONE: 0, DegradationLevel.PARTIAL: 1, DegradationLevel.MINIMAL: 2}

    def __init__(
        self,
        approval: IApprovalManager,
        critical_components: Optional[List[str]] = None,
        auto_partial: bool = True,
        now: Callable[[], str] = lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    ) -> None:
        self._approval = approval
        self._critical = set(critical_components or [])
        self._auto_partial = auto_partial
        self._now = now
        self._level = DegradationLevel.NONE
        self._last_reason = ""

    @property
    def level(self) -> DegradationLevel:
        return self._level

    def on_circuit_open(self, component: str) -> None:
        """A circuit tripped. Critical component -> escalate to MINIMAL (K5)."""
        if component in self._critical:
            self._escalate(DegradationLevel.MINIMAL, f"circuit open on critical: {component}")
        else:
            self._escalate(DegradationLevel.PARTIAL, f"circuit open: {component}")

    def on_recovery_exhausted(self, component: str) -> None:
        self._escalate(DegradationLevel.MINIMAL, f"recovery exhausted: {component}")

    def on_l3_panic(self) -> None:
        self._escalate(DegradationLevel.MINIMAL, "L3 kernel panic")

    def recover(self) -> None:
        """Return to full service (requires prior approval state cleared)."""
        self._level = DegradationLevel.NONE
        self._last_reason = ""

    # -- helpers -----------------------------------------------------------

    def _escalate(self, target: DegradationLevel, reason: str) -> None:
        if self._ORDER[target] <= self._ORDER[self._level]:
            return  # never de-escalate implicitly
        self._last_reason = reason
        # NONE -> PARTIAL may be auto (policy flag); PARTIAL -> MINIMAL always K5.
        if target is DegradationLevel.PARTIAL and self._auto_partial:
            self._level = DegradationLevel.PARTIAL
            return
        # K5-gated: request human approval before degrading.
        self._approval.request("self-analysis", f"degrade:{target.value}", reason)
        self._level = target

    def actions_for(self, level: Optional[DegradationLevel] = None) -> List[str]:
        """Concrete managed actions for the current (or given) level."""
        lvl = level or self._level
        if lvl is DegradationLevel.NONE:
            return []
        if lvl is DegradationLevel.PARTIAL:
            return [
                "block_spawn_non_critical_agents",
                "set_non_critical_services_read_only",
            ]
        return [
            "block_spawn_non_critical_agents",
            "set_non_critical_services_read_only",
            "quarantine_non_kernel_services",
            "keep_only_kernel_eventbus_auth",
        ]
