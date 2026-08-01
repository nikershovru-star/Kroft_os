"""SupervisorService — autonomous recovery orchestrator (Phase 4).

Observe -> Decide -> Recover -> Verify (not just Observe -> Report).

Design (preserves LAW K8):
- The Supervisor knows ONLY ports: IComponentController (restart abstraction),
  IProcessRegistry (read state), IEventBus (publish), RecoveryPolicyRegistry,
  RecoveryJournal, RecoveryState. It NEVER imports services/adapters/plugins, and
  NEVER builds an instance itself — restart goes through IComponentController, whose
  concrete impl (composition root) wires ComponentRegistry + InstanceBuilder.
- Policy-driven backoff (no hard-coded delays). On exhaustion -> QUARANTINED.
- Panic levels: L1 component failure -> restart; L2 runtime failure -> snapshot+recover;
  L3 kernel panic -> emergency shutdown (emitted on the bus, handled by kernel).

Imports ONLY contracts + local runtime modules + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from contracts import (
    IComponentController,
    IEventBus,
    IProcessRegistry,
    ProcessState,
)

from runtime.recovery.recovery_journal import RecoveryJournal
from runtime.recovery.recovery_state import RecoveryState
from runtime.recovery.strategy import build_strategy
from runtime.supervisor.recovery_policy import RecoveryPolicyRegistry
from runtime.supervisor.exceptions import ComponentFailure, KernelPanic, RuntimeFailure


class SupervisorService:
    """Drives recovery decisions for registered components."""

    def __init__(
        self,
        bus: IEventBus,
        registry: IProcessRegistry,
        controller: IComponentController,
        policies: RecoveryPolicyRegistry,
        journal: Optional[RecoveryJournal] = None,
        state: Optional[RecoveryState] = None,
        logger: Any = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._controller = controller
        self._policies = policies
        self._journal = journal or RecoveryJournal()
        self._state = state or RecoveryState(policies._policies if policies else None)
        self._log = logger
        self._sleep = sleep_fn
        bus.subscribe("component.failure", self._on_component_failure)
        bus.subscribe("runtime.failure", self._on_runtime_failure)
        bus.subscribe("kernel.panic", self._on_kernel_panic)

    # --- Level 1: component exception -> Supervisor.restart ----------------
    def _on_component_failure(self, event: dict) -> None:
        name = event.get("name", "")
        failure = event.get("error", "unknown")
        self.recover(name, failure)

    def recover(self, component: str, failure: str) -> ProcessState:
        """Attempt to recover a failed component (one attempt). Returns new state."""
        policy = self._policies.policy_for(component)
        if not policy.restart:
            # No restart allowed -> quarantine immediately.
            self._quarantine(component, failure, reason="restart disabled by policy")
            return ProcessState.QUARANTINED

        self._state.record_failure(component, failure)
        attempt = self._state.attempts(component)
        if self._state.is_exhausted(component):
            return self._quarantine(component, failure, reason="max attempts exceeded")

        # RECOVERING, then restart via the port (controller builds the instance).
        self._bus.publish_sync("component.recovering", {"name": component, "attempt": attempt})
        ok = self._controller.restart(component)
        result = "success" if ok else "failed"
        new_state = ProcessState.RUNNING if ok else ProcessState.FAILED
        if self._journal:
            self._journal.record(component, failure, attempt, result)
        if ok:
            self._state.reset(component)
            self._bus.publish_sync("component.recovered", {"name": component, "attempt": attempt})
            if self._log:
                self._log.info("component.recovered", name=component, attempt=attempt)
        else:
            if self._log:
                self._log.warn("component.recover.failed", name=component, attempt=attempt)
        return new_state

    def _quarantine(self, component: str, failure: str, reason: str) -> ProcessState:
        # Drive the process to QUARANTINED via the registry if reachable.
        proc = self._registry.get(component)
        if proc is not None and hasattr(proc, "_state"):
            try:
                proc._state = ProcessState.QUARANTINED
            except Exception:
                pass
        if self._journal:
            self._journal.record(component, failure, self._state.attempts(component), "quarantined")
        self._bus.publish_sync("component.quarantined", {"name": component, "reason": reason})
        if self._log:
            self._log.warn("component.quarantined", name=component, reason=reason)
        return ProcessState.QUARANTINED

    # --- Level 2: runtime exception -> Snapshot + Recovery ------------------
    def _on_runtime_failure(self, event: dict) -> None:
        self._bus.publish_sync("snapshot.request", {"reason": "runtime_failure"})
        self._bus.publish_sync("runtime.recovery", {"error": event.get("error", "unknown")})
        if self._log:
            self._log.warn("runtime.failure", error=event.get("error"))

    # --- Level 3: kernel panic -> Emergency shutdown -----------------------
    def _on_kernel_panic(self, event: dict) -> None:
        self._bus.publish_sync("snapshot.request", {"reason": "kernel_panic"})
        if self._log:
            self._log.error("kernel.panic", error=event.get("error"))
        # The kernel handles the actual stop; supervisor only logs + snapshots.

    # --- helper: compute backoff delay for a component's next attempt ------
    def backoff_delay(self, component: str) -> float:
        policy = self._policies.policy_for(component)
        strategy = build_strategy(policy)
        attempt = self._state.attempts(component)
        return strategy.delay_for(attempt)
