"""Tests for Wave 2 WP-10 (Circuit Breaker + Graceful Degradation + Agent Integration).

Targets >=18 tests. Includes negative proof-of-fire (K1: circuit_breaker does
not import services; K6: supervisor does not import healing.py internals).
"""
from __future__ import annotations

from tests._repo_root import repo_root
from pathlib import Path

REPO_ROOT = repo_root()
from typing import Optional

import pytest

from runtime.supervisor.circuit_breaker import CircuitBreaker, CircuitState
from runtime.supervisor.degradation import GracefulDegradationPolicy, DegradationLevel
from runtime.supervisor.supervisor_service import SupervisorService
from kernel.agent_lifecycle import AgentLifecycleFSM, AgentState
from services.agent_orchestration.healing import AgentRecoveryAdapter, SelfHealingPolicy
from infrastructure.eventbus import InMemoryEventBus
from kernel.security.approval_manager import ApprovalManager
from runtime.supervisor.recovery_policy import RecoveryPolicyRegistry


# --------------------------------------------------------------------------- #
# CircuitBreaker transitions
# --------------------------------------------------------------------------- #

class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_cb_closed_initial():
    cb = CircuitBreaker("c", failure_threshold=3, clock=_Clock())
    assert cb.current_state is CircuitState.CLOSED
    assert cb.trip_count == 0
    assert cb.allow_request() is True


def test_cb_closed_to_open_on_threshold():
    cb = CircuitBreaker("c", failure_threshold=3, clock=_Clock())
    for _ in range(3):
        cb.on_failure()
    assert cb.current_state is CircuitState.OPEN
    assert cb.trip_count == 1
    assert cb.allow_request() is False


def test_cb_open_to_half_open_after_cooldown():
    clk = _Clock()
    cb = CircuitBreaker("c", failure_threshold=3, clock=clk)
    for _ in range(3):
        cb.on_failure()
    assert cb.current_state is CircuitState.OPEN
    clk.t = 1000.0  # cooldown elapsed
    assert cb.current_state is CircuitState.HALF_OPEN
    assert cb.allow_request() is True


def test_cb_half_open_to_closed_on_success():
    clk = _Clock()
    cb = CircuitBreaker("c", failure_threshold=3, clock=clk)
    for _ in range(3):
        cb.on_failure()
    clk.t = 1000.0
    assert cb.current_state is CircuitState.HALF_OPEN
    cb.on_success()
    assert cb.current_state is CircuitState.CLOSED
    assert cb.trip_count == 1


def test_cb_half_open_to_open_on_failure():
    clk = _Clock()
    cb = CircuitBreaker("c", failure_threshold=3, clock=clk)
    for _ in range(3):
        cb.on_failure()
    clk.t = 1000.0
    assert cb.current_state is CircuitState.HALF_OPEN
    cb.on_failure()  # probe failed
    assert cb.current_state is CircuitState.OPEN
    assert cb.trip_count == 2


def test_cb_metrics_trip_count():
    clk = _Clock()
    cb = CircuitBreaker("c", failure_threshold=2, clock=clk)
    for _ in range(2):
        cb.on_failure()
    assert cb.current_state is CircuitState.OPEN
    clk.t = 1000.0
    assert cb.current_state is CircuitState.HALF_OPEN  # triggers transition
    cb.on_failure()  # half-open probe fail -> trip 2
    assert cb.trip_count == 2


# --------------------------------------------------------------------------- #
# GracefulDegradation
# --------------------------------------------------------------------------- #

def test_deg_none_initial():
    p = GracefulDegradationPolicy(ApprovalManager(), critical_components=["auth"])
    assert p.level is DegradationLevel.NONE
    assert p.actions_for() == []


def test_deg_non_critical_open_partial_auto():
    p = GracefulDegradationPolicy(ApprovalManager(), critical_components=["auth"], auto_partial=True)
    p.on_circuit_open("search-svc")
    assert p.level is DegradationLevel.PARTIAL
    assert "block_spawn_non_critical_agents" in p.actions_for()


def test_deg_critical_open_minimal_k5():
    p = GracefulDegradationPolicy(ApprovalManager(), critical_components=["auth"])
    p.on_circuit_open("auth")  # MINIMAL requires approval (K5)
    assert p.level is DegradationLevel.MINIMAL
    assert "keep_only_kernel_eventbus_auth" in p.actions_for()


def test_deg_recovery_none():
    p = GracefulDegradationPolicy(ApprovalManager(), critical_components=["auth"])
    p.on_circuit_open("auth")
    assert p.level is DegradationLevel.MINIMAL
    p.recover()
    assert p.level is DegradationLevel.NONE


def test_deg_l3_panic_minimal():
    p = GracefulDegradationPolicy(ApprovalManager(), critical_components=["auth"])
    p.on_l3_panic()
    assert p.level is DegradationLevel.MINIMAL


# --------------------------------------------------------------------------- #
# Agent integration (Supervisor -> IAgentRecovery via EventBus)
# --------------------------------------------------------------------------- #

class _NullRegistry:
    def get(self, name): return None


class _NullController:
    def restart(self, name): return True


def _build_supervisor(bus, fsm, approval, critical=("auth",)):
    adapter = AgentRecoveryAdapter(fsm, SelfHealingPolicy())
    deg = GracefulDegradationPolicy(approval, critical_components=list(critical))
    return SupervisorService(
        bus=bus,
        registry=_NullRegistry(),
        controller=_NullController(),
        policies=RecoveryPolicyRegistry(),
        agent_recovery=adapter,
        degradation=deg,
    )


def test_agent_stale_triggers_restart_via_supervisor():
    bus = InMemoryEventBus()
    fsm = AgentLifecycleFSM(bus=bus)
    fsm.spawn("a1", "acme", "Operator", "goal")
    sup = _build_supervisor(bus, fsm, ApprovalManager())
    assert fsm.get_state("a1") is AgentState.RUNNING
    fsm.transition("a1", AgentState.STALE, "no heartbeat")
    assert fsm.get_state("a1") is AgentState.RUNNING  # supervisor restarted it


def test_agent_failure_updates_circuit_and_degrades():
    bus = InMemoryEventBus()
    fsm = AgentLifecycleFSM(bus=bus)
    fsm.spawn("a1", "acme", "Operator", "goal")
    approval = ApprovalManager()
    sup = _build_supervisor(bus, fsm, approval, critical=("a1",))
    # 5 terminal failures on the SAME agent -> circuit OPEN -> critical -> MINIMAL (K5)
    for _ in range(5):
        sup._on_agent_failure({"agent_id": "a1", "error": "crash"})
    assert sup._agent_circuits["a1"].current_state is CircuitState.OPEN
    assert sup._degradation.level is DegradationLevel.MINIMAL


def test_agent_recovery_adapter_restart():
    fsm = AgentLifecycleFSM()
    fsm.spawn("a1", "acme", "Operator", "goal")
    fsm.transition("a1", AgentState.STALE, "x")
    adapter = AgentRecoveryAdapter(fsm, SelfHealingPolicy())
    assert adapter.restart_agent("a1") is True
    assert fsm.get_state("a1") is AgentState.RUNNING


def test_agent_recovery_adapter_quarantine():
    fsm = AgentLifecycleFSM()
    fsm.spawn("a1", "acme", "Operator", "goal")
    adapter = AgentRecoveryAdapter(fsm, SelfHealingPolicy())
    assert adapter.quarantine_agent("a1") is True
    assert fsm.get_state("a1") is AgentState.TERMINATED


def test_agent_recovery_adapter_health():
    fsm = AgentLifecycleFSM()
    fsm.spawn("a1", "acme", "Operator", "goal")
    adapter = AgentRecoveryAdapter(fsm, SelfHealingPolicy())
    assert adapter.get_agent_health("a1") is AgentState.RUNNING


# --------------------------------------------------------------------------- #
# Negative proof-of-fire (LAW enforcement)
# --------------------------------------------------------------------------- #

def test_k1_circuit_breaker_no_services_import():
    src = open(REPO_ROOT / "runtime/supervisor/circuit_breaker.py", encoding="utf-8").read()
    assert "import services" not in src and "from services" not in src
    assert "import kernel" not in src and "from kernel" not in src


def test_k8_supervisor_no_services_or_kernel_import():
    src = open(REPO_ROOT / "runtime/supervisor/supervisor_service.py", encoding="utf-8").read()
    assert "import services" not in src and "from services" not in src
    assert "import kernel" not in src and "from kernel" not in src


def test_k6_supervisor_does_not_import_healing_directly():
    # Supervisor must use the IAgentRecovery port, not healing.py internals.
    src = open(REPO_ROOT / "runtime/supervisor/supervisor_service.py", encoding="utf-8").read()
    assert "from services.agent_orchestration.healing import" not in src
    assert "import healing" not in src
