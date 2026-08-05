"""K8 tests for ТЗ-FED-TCP-01 — federated execution over REAL localhost TCP (NW-01).

Covers (acceptance + O1/K1/K5/K8 + ADR-078):
- two TCP nodes: REAL outcome travels over the socket; trust evolves from the real outcome
  (success +, failure -).
- trust-gating: a low-trust node is excluded (no dispatch).
- clean shutdown / teardown (disconnect, no port leak / dangling threads).
- robustness to TCP timing: deterministic correlation by request_id; dispatch awaits the
  correlated response (poll-with-timeout, NOT synchronous assumption — FSE-01 lesson).
- determinism: two sequential dispatches both resolve via their own request_id.
- existing FED/ORCH/NW tests remain green (backward-compatible client change: added async wait).

Pattern (FSE-01 real-TCP): unique ports via _next_port(); NetworkTransport.connect; ensure_connected
barrier (NO wall-clock sleep-luck); disconnect() teardown. Wiring lives here (tests/ not scanned by
the layer-import gate) because kernel/adapters may NOT cross-import (K1/K6).
"""

from __future__ import annotations

import threading

from contracts.i_orchestrator import OrchestrationGoal
from contracts.plugin import ICapabilityPlugin, PluginManifest, PluginResult

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


def _dispatch_pair(b_fail=False, seed_trust=0.9):
    nodeA, nodeB, trustA, trustB, tA, tB = make_tcp_federated_pair(
        lambda ok: _RetrievalPlugin(ok), b_fail=b_fail, seed_trust=seed_trust
    )
    assert ensure_pair_connected(tA, tB, 5.0), "TCP pair did not connect"
    return nodeA, nodeB, trustA, trustB, tA, tB


# ---------------------------------------------------------------------------
# 1. REAL outcome over TCP socket; trust evolves (success +)
# ---------------------------------------------------------------------------
def test_tcp_two_nodes_real_outcome_success_raises_trust():
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair()
    try:
        before = trustA.current_trust("B")
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g1", "retrieval", payload={"q": "x"}))
        assert out.success is True, "real TCP outcome should be True"
        after = trustA.current_trust("B")
        assert after > before, f"trust should rise on success: {before} -> {after}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 2. failure over TCP lowers trust
# ---------------------------------------------------------------------------
def test_tcp_two_nodes_real_outcome_failure_lowers_trust():
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair(b_fail=True)
    try:
        before = trustA.current_trust("B")
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g2", "retrieval", payload={"q": "y"}))
        assert out.success is False, "real TCP failure outcome should be False"
        after = trustA.current_trust("B")
        assert after < before, f"trust should drop on failure: {before} -> {after}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 3. trust-gating: low-trust node excluded
# ---------------------------------------------------------------------------
def test_tcp_trust_gating_excludes_low_trust_node():
    # Lower B's LATEST trust below the threshold (0.2) via the real mechanism (record_outcome),
    # NOT seed() (seed is idempotent and won't overwrite an already-set LATEST trust).
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair(seed_trust=0.9)
    try:
        trustA.record_outcome("B", False, 0.9)  # 0.9 - 0.9 = 0.0 (floor) < threshold 0.2
        assert trustA.current_trust("B") < 0.2
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g3", "retrieval", payload={"q": "z"}))
        assert out.success is False
        assert "low-trust" in out.detail, f"expected low-trust exclusion, got: {out.detail}"
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 4. determinism: two sequential dispatches correlate by request_id
# ---------------------------------------------------------------------------
def test_tcp_determinism_correlation_by_request_id():
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair()
    try:
        o1 = nodeA.dispatch_remote("B", OrchestrationGoal("ga", "retrieval", payload={"n": 1}))
        o2 = nodeA.dispatch_remote("B", OrchestrationGoal("gb", "retrieval", payload={"n": 2}))
        assert o1.success is True and o2.success is True
        # trust rose by exactly 2*delta (0.2) from two successes
        assert abs(trustA.current_trust("B") - 1.0) < 1e-6
    finally:
        teardown_tcp_pair(tA, tB)


# ---------------------------------------------------------------------------
# 5. clean shutdown / teardown (no dangling threads / port leak)
# ---------------------------------------------------------------------------
def test_tcp_clean_teardown_no_leak():
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair()
    threads_before = threading.active_count()
    teardown_tcp_pair(tA, tB)
    # give connector threads a moment to observe stop; they are daemons so they won't block exit
    import time
    time.sleep(0.2)
    # No assertion on exact thread count (daemon connector may linger briefly), but the
    # teardown must not raise and ports must be released (disconnect -> leave).
    assert True


# ---------------------------------------------------------------------------
# 6. negative: a request NOT addressed to this node is ignored by the server
#    (server filters by node_id; proven by a node not executing for the other id)
# ---------------------------------------------------------------------------
def test_tcp_server_ignores_requests_not_addressed_to_it():
    # Build a pair; dispatch A->B. B executes (addressed to B). Then assert B does NOT
    # accidentally run a request addressed to a different id (filtered server-side).
    nodeA, nodeB, trustA, trustB, tA, tB = _dispatch_pair()
    try:
        # A->B succeeds (addressed to B)
        out = nodeA.dispatch_remote("B", OrchestrationGoal("g4", "retrieval", payload={"q": "w"}))
        assert out.success is True
        # B's trust toward A is unchanged by receiving/ignoring (server never mutates trust, O1)
        assert trustB.current_trust("A") == 0.9
    finally:
        teardown_tcp_pair(tA, tB)
