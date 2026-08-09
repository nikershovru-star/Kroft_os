"""K8 tests for ТЗ-NET-AGENT-EXEC-01 — network multi-agent execution (real agent tick on remote node).

Closes the Tachikoma vision: a goal routed to an agent is executed by a REAL agent tick on a
REMOTE node, and trust evolves from the REAL network outcome (success +, failure -).

Covers (acceptance + O1/K1/K6/K8 + ADR-081):
- remote agent execution: A.dispatch_remote(agent_goal -> B) -> B routes to its local agent,
  runs ReferenceAgentExecutor (REAL cognitive tick), real TaskOutcome returns over the socket to A.
- trust evolves from the REAL network outcome: success raises A's trust toward B; a forced
  agent FAILURE on B lowers it (honest, not delegated success=True).
- backward-compat: WITHOUT agent_executor on B (or without agent_capability registered), the
  dispatch keeps its PREVIOUS behaviour (plugin / delegated) — no regression.
- determinism (I-09): LLM-free agent tick; two sequential dispatches resolve by request_id.
- O1: trust is SOFT (via ITrustRegistry.record_outcome); the server never mutates remote trust.
- existing FED/AGENT/ORCH tests remain green (this change is additive + optional-param end-to-end).

Pattern: reuse make_tcp_federated_pair with agent_executor + agent_capability (real localhost TCP,
Флаг 1 fix 321fc21). ensure_connected barrier (NO sleep-luck). Wiring in tests/ (not scanned by
the layer-import gate) because kernel/adapters may NOT cross-import (K1/K6).
"""

from __future__ import annotations
import pytest

import threading

from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.plugin import ICapabilityPlugin, PluginManifest, PluginResult

from kernel.agent_executor import ReferenceAgentExecutor, build_agent_executor

from tests.common.fed_tcp_helpers import (
    ensure_pair_connected,
    make_tcp_federated_pair,
    teardown_tcp_pair,
)


class _RetrievalPlugin(ICapabilityPlugin):
    def __init__(self, ok: bool):
        self._ok = ok

    @property
    def id(self) -> str:
        return "p_retrieval"

    @property
    def name(self) -> str:
        return "retrieval"

    @property
    def capabilities(self):
        return ("retrieval",)

    def manifest(self) -> PluginManifest:
        return PluginManifest(id=self.id, name=self.name, capabilities=self.capabilities)

    def invoke(self, args):
        return PluginResult(ok=self._ok, payload=None, error=None if self._ok else "boom")


def _agent_pair(agent_fail=False, seed_trust=0.9):
    """Two TCP nodes; B has a REAL agent executor for capability 'plan'."""
    nodeA, nodeB, trustA, trustB, tA, tB = make_tcp_federated_pair(
        lambda ok: _RetrievalPlugin(ok),
        seed_trust=seed_trust,
        agent_executor=build_agent_executor("B-agent"),
        agent_capability="plan",
    )
    assert ensure_pair_connected(tA, tB, 5.0), "TCP pair did not connect"
    return nodeA, nodeB, trustA, trustB, tA, tB


# ---------------------------------------------------------------------------
# 1. REMOTE agent execution: real outcome from agent tick on remote node
# ---------------------------------------------------------------------------
def test_remote_agent_execution_real_outcome_from_agent_tick():
    nodeA, nodeB, trustA, trustB, tA, tB = _agent_pair()
    try:
        # Goal with agent-capability 'plan' addressed to B -> B routes to its agent,
        # runs a REAL cognitive tick, returns the computed TaskOutcome over the socket.
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g1", "plan", payload="do it"))
        assert out.success is True, "remote real agent tick should yield success"
        assert "agent tick" in out.detail, f"expected real agent outcome, got: {out.detail}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 2. trust evolves from REAL network outcome: success raises
# ---------------------------------------------------------------------------
def test_remote_agent_execution_success_raises_trust():
    nodeA, nodeB, trustA, trustB, tA, tB = _agent_pair()
    try:
        before = trustA.current_trust("B")
        nodeA.dispatch_remote("B", OrchestrationGoal("g2", "plan", payload="x"))
        after = trustA.current_trust("B")
        assert after > before, f"trust should rise on real remote success: {before} -> {after}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 3. trust evolves from REAL network outcome: forced agent FAILURE lowers
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_remote_agent_execution_failure_lowers_trust():
    nodeA, nodeB, trustA, trustB, tA, tB = _agent_pair()
    try:
        # Force a real failure outcome from B's agent executor (simulates a tick that failed
        # to plan/execute) — without touching the network path. This proves trust evolves from
        # the REAL agent outcome, not a delegated success=True.
        class FailingAgentExecutor(ReferenceAgentExecutor):
            def execute(self, goal):
                return TaskOutcome(success=False, detail="agent tick: no plan selected/executed")

        # Rebuild the pair with a failing executor to exercise the failure branch.
        teardown_tcp_pair(tA, tB)
        nodeA, nodeB, trustA, trustB, tA, tB = make_tcp_federated_pair(
            lambda ok: _RetrievalPlugin(ok),
            seed_trust=0.9,
            agent_executor=FailingAgentExecutor("B-agent"),
            agent_capability="plan",
        )
        assert ensure_pair_connected(tA, tB, 5.0), "TCP pair did not connect"
        before = trustA.current_trust("B")
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g3", "plan", payload="y"))
        assert out.success is False, "remote real agent FAILURE must return False"
        after = trustA.current_trust("B")
        assert after < before, f"trust should drop on real remote failure: {before} -> {after}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 4. backward-compat: WITHOUT agent_executor -> previous behaviour (no break)
# ---------------------------------------------------------------------------
def test_no_remote_agent_executor_keeps_previous_behaviour():
    # No agent_executor / agent_capability -> B executes via plugin (unchanged FED-EXEC path).
    nodeA, nodeB, trustA, trustB, tA, tB = make_tcp_federated_pair(
        lambda ok: _RetrievalPlugin(ok), seed_trust=0.9, b_fail=False,
    )
    try:
        assert ensure_pair_connected(tA, tB, 5.0), "TCP pair did not connect"
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g4", "retrieval", payload={"q": "z"}))
        assert out.success is True, "plugin path still works without agent_executor"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 5. determinism (I-09): two sequential remote agent dispatches resolve by request_id
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_remote_agent_execution_determinism_correlation_by_request_id():
    nodeA, nodeB, trustA, trustB, tA, tB = _agent_pair()
    try:
        o1 = nodeA.dispatch_remote("B", OrchestrationGoal("ga", "plan", payload="repeat"))
        o2 = nodeA.dispatch_remote("B", OrchestrationGoal("gb", "plan", payload="repeat"))
        assert o1.success is True and o2.success is True
        # both real agent successes -> trust rose by exactly 2*delta (0.2) from two successes
        assert abs(trustA.current_trust("B") - 1.0) < 1e-6
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 6. O1: trust is SOFT; server (B) never mutates remote (A's) trust
# ---------------------------------------------------------------------------
def test_remote_agent_execution_o1_server_does_not_mutate_remote_trust():
    nodeA, nodeB, trustA, trustB, tA, tB = _agent_pair()
    try:
        nodeA.dispatch_remote("B", OrchestrationGoal("g5", "plan", payload="z"))
        # B received/executed the request but its trust toward A is UNCHANGED (server never
        # mutates remote trust, O1). Only A's trust toward B evolves (client side).
        assert trustB.current_trust("A") == 0.9
    finally:
        teardown_tcp_pair(tA, tB)
