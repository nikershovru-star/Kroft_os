"""Recovery state — per-component attempt tracking + quarantine decisions.

Per Phase 4: tracks consecutive failures per component and decides RECOVERING vs
QUARANTINED based on the RecoveryPolicy. Pure state holder; no platform imports.
Imports ONLY contracts + local recovery modules + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

from typing import Dict

from contracts import ProcessState

from runtime.recovery.policy import RecoveryPolicy


class RecoveryState:
    """Tracks restart attempts per component and applies the policy."""

    def __init__(self, policies: Dict[str, RecoveryPolicy] | None = None,
                 default_policy: RecoveryPolicy | None = None) -> None:
        self._policies = policies or {}
        self._default = default_policy or RecoveryPolicy()
        self._attempts: Dict[str, int] = {}
        self._failures: Dict[str, str] = {}

    def policy_for(self, component: str) -> RecoveryPolicy:
        return self._policies.get(component, self._default)

    def record_failure(self, component: str, failure: str) -> None:
        self._attempts[component] = self._attempts.get(component, 0) + 1
        self._failures[component] = failure

    def attempts(self, component: str) -> int:
        return self._attempts.get(component, 0)

    def last_failure(self, component: str) -> str:
        return self._failures.get(component, "unknown")

    def reset(self, component: str) -> None:
        self._attempts[component] = 0

    def next_state(self, component: str) -> ProcessState:
        """Decide RECOVERING or QUARANTINED for the current attempt count."""
        policy = self.policy_for(component)
        attempt = self.attempts(component)
        if not policy.restart:
            return ProcessState.QUARANTINED
        if policy.should_quarantine(attempt):
            return ProcessState.QUARANTINED
        return ProcessState.RECOVERING

    def is_exhausted(self, component: str) -> bool:
        policy = self.policy_for(component)
        return policy.should_quarantine(self.attempts(component))
