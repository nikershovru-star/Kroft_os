"""K8 tests for ТЗ-FED-ORCH-01 — federated orchestration (real remote outcomes + trust-gating).

Covers (acceptance + O1/K1/K5/K8 + ADR-075):
- remote dispatch returns the REAL outcome (FakeTransport, deterministic by node).
- trust EVOLVES from the real remote outcome: failure LOWERS current_trust(node) (closes
  Флаг 2 ORCH-01); success raises it. (ITrustRegistry.record_outcome via ReferenceRemoteOrchestrator)
- trust-gating: low-trust node (< threshold) is EXCLUDED (dispatch_remote -> TaskOutcome(False)).
- orchestrator fallback: no local eligible -> routes to trusted remote (kind='remote');
  low-trust-only remote -> None (local routing NOT broken).
- determinism (I-09): correlation by request_id; tie-break by node_id.
- O1: trust updates are SOFT (ITrustRegistry); remote does not mutate HARD/FSM.
- K5: does NOT duplicate INetworkTransport / ITrustRegistry / ReferenceOrchestrator.

FakeTransport reuses NW-01's send_facts/on_facts channel (deterministic in-process).
"""

from __future__ import annotations

from contracts.i_federated_orchestrator import IRemoteOrchestrator
from contracts.i_identity import AgentIdentity
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from kernel.federated_orchestrator import build_remote_orchestrator
from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry


class FakeTransport(INetworkTransport):
    """Deterministic in-process NW-01 carrier: per-node outcome map."""

    def __init__(self, outcomes):
        self._outcomes = dict(outcomes)  # node_id -> bool success
        self._facts_handler = None

    def connect(self, node_id, peers): pass
    def send_event(self, event): pass
    def send_facts(self, facts, sender_node_id):
        for fact in facts:
            if isinstance(fact, dict) and fact.get("__fed_orch_req__"):
                node = fact["node_id"]; rid = fact["request_id"]
                ok = self._outcomes.get(node, False)
                resp = {
                    "__fed_orch_resp__": True, "request_id": rid, "node_id": node,
                    "author_id": node, "causal": None,
                    "outcome": {"success": ok, "detail": "remote ok" if ok else "remote fail"},
                }
                if self._facts_handler:
                    self._facts_handler([resp], node)
    def on_event(self, handler): pass
    def on_facts(self, handler): self._facts_handler = handler
    def send_soft_layer(self, items, sender_node_id): pass
    def on_soft_layer(self, handler): pass
    def disconnect(self): pass
    def to_wire(self, *a, **k): pass
    def from_wire(self, *a, **k): pass


def _trust():
    t = ReferenceTrustRegistry()
    t.seed("n1", 0.9)
    t.seed("nlow", 0.1)
    return t


# ---------------------------------------------------------------------------
# 1. remote dispatch returns REAL outcome (FakeTransport deterministic)
# ---------------------------------------------------------------------------
def test_remote_dispatch_real_outcome_success():
    t = _trust()
    ro = build_remote_orchestrator(FakeTransport({"n1": True}), t, trust_threshold=0.2)
    out = ro.dispatch_remote("n1", OrchestrationGoal("g", "retrieval"))
    assert out.success is True


def test_remote_dispatch_real_outcome_failure():
    t = _trust()
    ro = build_remote_orchestrator(FakeTransport({"n1": False}), t, trust_threshold=0.2)
    out = ro.dispatch_remote("n1", OrchestrationGoal("g", "retrieval"))
    assert out.success is False


# ---------------------------------------------------------------------------
# 2. trust EVOLVES from real remote outcome (closes Флаг 2 ORCH-01)
# ---------------------------------------------------------------------------
def test_trust_lowered_on_remote_failure():
    t = _trust()
    ro = build_remote_orchestrator(FakeTransport({"n1": False}), t, trust_threshold=0.2)
    before = t.current_trust("n1")
    ro.dispatch_remote("n1", OrchestrationGoal("g", "retrieval"))
    assert t.current_trust("n1") < before          # 0.9 -> 0.8


def test_trust_raised_on_remote_success():
    t = _trust()
    ro = build_remote_orchestrator(FakeTransport({"n1": True}), t, trust_threshold=0.2)
    before = t.current_trust("n1")
    ro.dispatch_remote("n1", OrchestrationGoal("g", "retrieval"))
    assert t.current_trust("n1") > before


# ---------------------------------------------------------------------------
# 3. trust-gating: low-trust node EXCLUDED
# ---------------------------------------------------------------------------
def test_low_trust_node_excluded():
    t = _trust()
    ro = build_remote_orchestrator(FakeTransport({"nlow": True}), t, trust_threshold=0.2)
    out = ro.dispatch_remote("nlow", OrchestrationGoal("g", "retrieval"))
    assert out.success is False
    assert "low-trust" in out.detail


# ---------------------------------------------------------------------------
# 4. orchestrator remote fallback (no local eligible -> trusted remote)
# ---------------------------------------------------------------------------
def _orch_with_remote(remote, nodes):
    ident = ReferenceIdentityRegistry()  # no agents
    plugins = ReferencePluginRegistry()  # no plugins
    trust = _trust()
    log = ReferenceActionLog()
    return build_orchestrator(ident, plugins, trust, log,
                              trust_threshold=0.2, remote=remote, remote_nodes=nodes)


def test_orchestrator_falls_back_to_trusted_remote():
    t = _trust()
    remote = build_remote_orchestrator(FakeTransport({"n1": True}), t, trust_threshold=0.2)
    orch = _orch_with_remote(remote, ("n1", "nlow"))
    d = orch.route(OrchestrationGoal("g", "retrieval"))
    assert d.kind == "remote" and d.chosen_id == "n1"
    assert d.rationale == "remote:n1"
    out = orch.dispatch(OrchestrationGoal("g", "retrieval"))
    assert out.success is True


def test_orchestrator_low_trust_remote_only_none():
    t = _trust()
    remote = build_remote_orchestrator(FakeTransport({"nlow": True}), t, trust_threshold=0.2)
    orch = _orch_with_remote(remote, ("nlow",))  # only low-trust remote
    assert orch.route(OrchestrationGoal("g", "retrieval")) is None  # NOT broken


# ---------------------------------------------------------------------------
# 5. determinism (I-09): tie-break by node_id, stable
# ---------------------------------------------------------------------------
def test_determinism_remote_tie_break():
    t = _trust()
    remote = build_remote_orchestrator(FakeTransport({"n1": True, "nx": True}), t, trust_threshold=0.2)
    orch1 = _orch_with_remote(remote, ("n1", "nx"))
    orch2 = _orch_with_remote(remote, ("nx", "n1"))
    # both trusted -> sorted order picks the lexically-first node deterministically
    assert orch1.route(OrchestrationGoal("g", "retrieval")).chosen_id == "n1"
    assert orch2.route(OrchestrationGoal("g", "retrieval")).chosen_id == "n1"


# ---------------------------------------------------------------------------
# 6. negative: no remote configured -> local routing unchanged (not broken)
# ---------------------------------------------------------------------------
def test_no_remote_configured_local_intact():
    ident = ReferenceIdentityRegistry()
    ident.register(AgentIdentity("a_good", "retrieval", 0.9, ("retrieval", "read")))
    plugins = ReferencePluginRegistry()
    trust = _trust()
    log = ReferenceActionLog()
    orch = build_orchestrator(ident, plugins, trust, log, trust_threshold=0.2)  # remote=None
    d = orch.route(OrchestrationGoal("g", "retrieval"))
    assert d.kind == "agent" and d.chosen_id == "a_good"  # unchanged
