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
from contracts.agent_orchestration import IAgentRecovery

from runtime.recovery.recovery_journal import RecoveryJournal
from runtime.recovery.recovery_state import RecoveryState
from runtime.recovery.strategy import build_strategy
from runtime.supervisor.recovery_policy import RecoveryPolicyRegistry
from runtime.supervisor.exceptions import ComponentFailure, KernelPanic, RuntimeFailure
from runtime.supervisor.circuit_breaker import CircuitBreaker, CircuitState
from runtime.supervisor.degradation import GracefulDegradationPolicy, DegradationLevel


class _NullApproval:
    """No-op approval (used when no ApprovalManager is injected)."""

    def request(self, agent_id: str, action: str, arguments: str):
        from contracts.security import ApprovalRequest, ApprovalStatus
        return ApprovalRequest(agent_id=agent_id, action=action, arguments=arguments,
                               status=ApprovalStatus.APPROVED)


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
        agent_recovery: Optional[IAgentRecovery] = None,
        degradation: Optional[GracefulDegradationPolicy] = None,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._controller = controller
        self._policies = policies
        self._journal = journal or RecoveryJournal()
        self._state = state or RecoveryState(policies._policies if policies else None)
        self._log = logger
        self._sleep = sleep_fn
        self._agent_recovery = agent_recovery
        self._degradation = degradation or GracefulDegradationPolicy(_NullApproval())
        self._agent_circuits: Dict[str, CircuitBreaker] = {}
        bus.subscribe("component.failure", self._on_component_failure)
        bus.subscribe("runtime.failure", self._on_runtime_failure)
        bus.subscribe("kernel.panic", self._on_kernel_panic)
        # Wave 2 WP-10: agent integration (K6 — only via EventBus)
        bus.subscribe("agent.stale", self._on_agent_stale)
        bus.subscribe("agent.failure", self._on_agent_failure)

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

    # --- Wave 2 WP-10: agent integration (K6, EventBus only) ---------------
    def _agent_circuit(self, agent_id: str) -> CircuitBreaker:
        cb = self._agent_circuits.get(agent_id)
        if cb is None:
            cb = CircuitBreaker(f"agent:{agent_id}")
            self._agent_circuits[agent_id] = cb
        return cb

    def _on_agent_stale(self, event: dict) -> None:
        agent_id = event.get("agent_id", "")
        if self._agent_recovery is None:
            return
        # Stale agent -> restart via the recovery port (never direct call, K6).
        ok = self._agent_recovery.restart_agent(agent_id)
        if self._log:
            self._log.warn("agent.restart", name=agent_id, ok=ok)

    def _on_agent_failure(self, event: dict) -> None:
        agent_id = event.get("agent_id", "")
        cb = self._agent_circuit(agent_id)
        cb.on_failure()
        if cb.current_state is CircuitState.OPEN:
            # Sustained agent failures -> escalate degradation (K5 on MINIMAL).
            self._degradation.on_circuit_open(agent_id)
            if self._log:
                self._log.error("agent.circuit.open", name=agent_id,
                                level=self._degradation.level.value)
        elif self._agent_recovery is not None:
            # Transient failure -> probe a restart.
            self._agent_recovery.restart_agent(agent_id)

    # --- helper: compute backoff delay for a component's next attempt ------
    def backoff_delay(self, component: str) -> float:
        policy = self._policies.policy_for(component)
        strategy = build_strategy(policy)
        attempt = self._state.attempts(component)
        return strategy.delay_for(attempt)
