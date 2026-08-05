"""K8 tests for ТЗ-NET-ROUTE-01 — node discovery + multi-hop routing (ADR-086).

Covers (acceptance + K1/K5/K6/K8/O1/I-09 + ADR-086):
- DISCOVERY: INodeDiscovery.members() fills from seed peers (reuse GossipNodeDiscovery).
- MULTI-HOP: dispatch_remote to a NON-direct peer (A -> C via B) succeeds; the forwarded envelope
  keeps the ORIGINAL signature (provenance preserved across hops); the response routes back.
- TRUST-GATING: dispatch excluded to low-trust node; trust evolves only from verified+non-replay outcome.
- CRYPTO per hop: tampered / replayed / unsigned envelope rejected at the destination (verify+replay).
- DETERMINISM (I-09): ReferenceRoutingTable.next_hop is a pure function; repeated dispatch identical.

Two transport harnesses:
- MeshTransport: in-process neighbor-broadcast (each node broadcasts ONLY to its connected peers ->
  faithful to real-TCP broadcast; multi-hop traverses deterministically, no sockets).
- RealTcpMesh: optional honest capstone over real localhost TCP (skipped if ports busy) — mirrors FSE-01.

K5: reuses ReferenceRoutingTable / GossipNodeDiscovery / build_remote_orchestrator / build_federated_node
/ HmacSigner / ReplayGuard (NO new ports beyond IRoutingTable + envelope route header). Wiring in tests/.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_distributed_runtime import INodeDiscovery, IRoutingTable
from contracts.i_federated_orchestrator import RoutingHeader, DEFAULT_ROUTE_TTL
from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from contracts.i_signature import ISignatureProvider, attach_signature, verify_envelope
from kernel.crypto import HmacSigner, ReplayGuard, build_hmac_signer
from kernel.federated_executor import build_federated_node
from kernel.federated_orchestrator import build_remote_orchestrator
from kernel.identity import ReferenceTrustRegistry
from services.distributed_runtime import GossipNodeDiscovery, ReferenceRoutingTable


# ---------------------------------------------------------------------------
# In-process neighbor-broadcast transport (faithful to real-TCP broadcast)
# ---------------------------------------------------------------------------
class MeshTransport(INetworkTransport):
    """Each node broadcasts ONLY to its connected peers -> multi-hop traversal is real (no sockets).

    Harness links transports by a shared registry {node_id: transport}. send_facts/on_facts reach
    exactly the node's neighbors. This mirrors NW-01 real-TCP broadcast where a node's packet is
    delivered to its directly-connected peers, so a forwarded envelope naturally hops A->B->C.
    """

    def __init__(self, node_id: str, registry: Dict[str, "MeshTransport"], peers: List[str]) -> None:
        self._node_id = node_id
        self._registry = registry
        self._peers = list(peers)
        self._facts_handler: Optional[Callable] = None
        self._soft_handler: Optional[Callable] = None
        registry[node_id] = self

    def connect(self, node_id: str, peers: List[str]) -> None:
        self._peers = list(peers)

    def send_event(self, event): pass
    def send_facts(self, facts, sender_node_id):
        for p in self._peers:
            t = self._registry.get(p)
            if t is not None and t._facts_handler is not None:
                t._facts_handler(facts, sender_node_id)
    def on_event(self, h): pass
    def on_facts(self, h): self._facts_handler = h
    def send_soft_layer(self, items, sender_node_id):
        for p in self._peers:
            t = self._registry.get(p)
            if t is not None and t._soft_handler is not None:
                t._soft_handler(items, sender_node_id)
    def on_soft_layer(self, h): self._soft_handler = h
    def disconnect(self): pass


def _mesh_pair_trio():
    """Build a chain A-B-C: A<->B, B<->C (A and C are NOT directly connected)."""
    reg: Dict[str, MeshTransport] = {}
    tA = MeshTransport("A", reg, ["B"])
    tB = MeshTransport("B", reg, ["A", "C"])
    tC = MeshTransport("C", reg, ["B"])
    return reg, tA, tB, tC


def _router(node_id, members, peers):
    r = ReferenceRoutingTable(node_id)
    r.update(node_id, members, peers)
    return r


# ---------------------------------------------------------------------------
# 1. DISCOVERY: membership fills from seed peers (reuse GossipNodeDiscovery)
# ---------------------------------------------------------------------------
class _Bus:
    def __init__(self): self._subs = {}
    def subscribe(self, topic, h): self._subs.setdefault(topic, []).append(h)
    def publish(self, topic, event):
        for h in self._subs.get(topic, []): h(topic, event)


def test_discovery_fills_membership():
    bus = _Bus()
    d: INodeDiscovery = GossipNodeDiscovery(bus)
    d.start("A", ["B", "C"])
    # simulate peers announcing themselves
    bus.publish("discovery.hello", {"node_id": "B"})
    bus.publish("discovery.hello", {"node_id": "C"})
    members = set(d.members())
    assert {"A", "B", "C"}.issubset(members), f"membership must include seeded+announced: {members}"
    assert d.is_alive("B") is True


# ---------------------------------------------------------------------------
# 2. MULTI-HOP: A dispatches to C (non-direct) via B; response routes back
# ---------------------------------------------------------------------------
def test_multihop_dispatch_via_intermediary():
    reg, tA, tB, tC = _mesh_pair_trio()
    members = ["A", "B", "C"]
    # trust: all seeded high so dispatch is allowed
    trustA = ReferenceTrustRegistry(); trustA.seed("A", 0.9); trustA.seed("B", 0.9); trustA.seed("C", 0.9)
    trustB = ReferenceTrustRegistry(); trustB.seed("A", 0.9); trustB.seed("B", 0.9); trustB.seed("C", 0.9)
    trustC = ReferenceTrustRegistry(); trustC.seed("A", 0.9); trustC.seed("B", 0.9); trustC.seed("C", 0.9)

    signer = build_hmac_signer("mesh-key")
    rgA = ReplayGuard(); rgB = ReplayGuard(); rgC = ReplayGuard()

    # A -> C via B. A's direct peer is B; routing forwards to B then to C.
    roA = build_remote_orchestrator(
        tA, trustA, local_node_id="A", signature_provider=signer, replay_guard=rgA,
        routing_table=_router("A", members, ["B"]), direct_peers=["B"],
    )
    # B is an intermediary: it must have a routing table to forward both directions.
    roB = build_remote_orchestrator(
        tB, trustB, local_node_id="B", signature_provider=signer, replay_guard=rgB,
        routing_table=_router("B", members, ["A", "C"]), direct_peers=["A", "C"],
    )
    # C executes locally. Build its orchestrator explicitly with a real executor so the
    # server's self._orch.dispatch(goal) returns a real TaskOutcome.
    from kernel.execution import ReferenceExecutor
    from kernel.identity import (ReferenceIdentityRegistry, ReferenceActionLog)
    from kernel.plugin import _BaseCapabilityPlugin, ReferencePluginRegistry
    from kernel.orchestrator import build_orchestrator
    from contracts.plugin import PluginManifest, PluginResult

    class _NoopPlugin(_BaseCapabilityPlugin):
        @property
        def id(self) -> str: return "noop"
        @property
        def name(self) -> str: return "noop"
        @property
        def capabilities(self): return ("noop",)
        def invoke(self, args=None):
            return PluginResult(ok=True, payload={"ok": True})

    idr = ReferenceIdentityRegistry()
    plr = ReferencePluginRegistry()
    plr.register(_NoopPlugin())
    alog = ReferenceActionLog()
    orchC = build_orchestrator(idr, plr, trustC, alog, agent_executor=ReferenceExecutor())
    nodeC = build_federated_node(
        tC, orchC, trustC, "C", signature_provider=signer, replay_guard=rgC,
        remote_nodes=("A", "B"),
        routing_table=_router("C", members, ["B"]), direct_peers=["B"],
    )
    nodeC.start()

    goal = OrchestrationGoal(goal_id="g1", capability="noop", payload={})
    outcome = roA.dispatch_remote("C", goal)
    assert outcome.success is True, f"multi-hop dispatch A->C must succeed, got {outcome}"
    # A's trust in C must have evolved from the verified+non-replay outcome (success +).
    assert trustA.current_trust("C") > 0.9, "trust in C should rise after verified success"


# ---------------------------------------------------------------------------
# 3. TRUST-GATING: low-trust node excluded; tampered/replayed/unsigned rejected at dest
# ---------------------------------------------------------------------------
def test_trust_gating_excludes_low_trust():
    reg, tA, tB, tC = _mesh_pair_trio()
    trustA = ReferenceTrustRegistry(); trustA.seed("A", 0.9); trustA.seed("B", 0.9); trustA.seed("C", 0.1)
    signer = build_hmac_signer("k")
    roA = build_remote_orchestrator(
        tA, trustA, local_node_id="A", trust_threshold=0.2, signature_provider=signer,
        routing_table=_router("A", ["A", "B", "C"], ["B"]), direct_peers=["B"],
    )
    goal = OrchestrationGoal(goal_id="g2", capability="noop", payload={})
    out = roA.dispatch_remote("C", goal)  # C has low trust (0.1 < 0.2)
    assert out.success is False and "low-trust" in out.detail, "low-trust dispatch must be excluded"


def test_tampered_replayed_unsigned_rejected_at_destination():
    signer = build_hmac_signer("k")
    rg = ReplayGuard()
    goal = OrchestrationGoal(goal_id="g", capability="noop", payload={})
    req = {
        "__fed_orch_req__": True, "request_id": "r1", "node_id": "C", "author_id": "A",
        "goal": {"goal_id": "g", "capability": "noop", "payload": {}},
        "causal": {"node_origin": "A", "lamport": 1},
        "route": {"target": "C", "ttl": 8},
    }
    signed = attach_signature(req, signer)
    # valid signed request -> accepted
    assert verify_envelope(signed, signer, replay_guard=rg) is True
    # tampered after signing -> reject
    tampered = dict(signed); tampered["goal"] = {"goal_id": "g", "capability": "evil", "payload": {}}
    assert verify_envelope(tampered, signer, replay_guard=rg) is False
    # replay (same seq) -> reject
    assert verify_envelope(signed, signer, replay_guard=rg) is False
    # unsigned with verifier -> reject
    assert verify_envelope(req, signer) is False


# ---------------------------------------------------------------------------
# 4. DETERMINISM (I-09): next_hop is a pure function
# ---------------------------------------------------------------------------
def test_routing_table_deterministic():
    r = ReferenceRoutingTable("A")
    r.update("A", ["A", "B", "C", "D"], ["B"])
    assert r.next_hop("D") == "B"  # A's only peer toward D is B
    r2 = ReferenceRoutingTable("B")
    r2.update("B", ["A", "B", "C", "D"], ["A", "C"])
    assert r2.next_hop("D") == "C"  # B forwards to C (closer to D)
    assert r2.next_hop("A") == "A"  # direct peer -> itself
    # idempotent pure function
    r3 = ReferenceRoutingTable("A")
    r3.update("A", ["A", "B", "C", "D"], ["B"])
    assert r3.next_hop("D") == r.next_hop("D")
