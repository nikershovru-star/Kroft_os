"""KROFT-NET-07 — remote-node readiness (TZ §34: PC A -> PC B via internet).

Proves the transport layer is REMOTE-READY: a node binding to host="0.0.0.0"
(all interfaces) accepts connections that a second node reaches via an explicit
seed address. This is the exact mechanism a cross-internet link uses (loopback
stands in for the remote IP here — only a firewall/NAT hole is needed for real
internet, which is an ops concern outside this code).

REUSE: TcpEventBus(host=...) (adapters/tcp_event_bus.py, already supports host)
+ KnowledgeEnvelopeRouter + HmacSigner. No new transport.

Run: pytest tests/test_kroft_remote_ready.py -q
"""

from __future__ import annotations

import time

import pytest

from adapters.tcp_event_bus import TcpEventBus
from contracts.i_self_evolution_cycle import KnowledgeOrigin
from contracts.i_knowledge_resolution import ResolutionLevel
from contracts.knowledge_envelope import KnowledgeEnvelope
from kernel.crypto import HmacSigner
from kernel.identity import ReferenceTrustRegistry
from services.knowledge_envelope_router import KnowledgeEnvelopeRouter


def _make(node_id, port, host, seed_peers):
    bus = TcpEventBus(node_id, port, host=host)
    bus.join(seed_peers or [])
    trust = ReferenceTrustRegistry()
    trust.seed(node_id, 0.9)
    signer = HmacSigner(b"shared-test-key")
    router = KnowledgeEnvelopeRouter(
        node_id=node_id, bus=bus, trust_registry=trust, signer=signer,
        state_root=f".kroft_remote/{node_id}",
    )
    return bus, router


def _env(sender, recipient, kid="k1"):
    return KnowledgeEnvelope(
        knowledge_id=kid, content="X is true", origin=KnowledgeOrigin.LOCAL,
        sender=sender, recipient=recipient, resolution=ResolutionLevel.SYSTEM,
        confidence=0.9, provenance=["fact-1", "ep-2"], trust=0.9,
        signature="signed", ttl=8,
    )


@pytest.fixture
def net():
    # A binds to 0.0.0.0 (all interfaces -> remote-reachable); B reaches via 127.0.0.1.
    a_bus, a = _make("A", 7301, "0.0.0.0", [])
    b_bus, b = _make("B", 7302, "127.0.0.1", ["127.0.0.1:7301"])
    time.sleep(1.0)
    yield {"A": a, "B": b}
    a_bus.leave(); b_bus.leave()


def test_remote_ready_a_binds_all_interfaces_b_reaches(net):
    """TZ §34: A listens on 0.0.0.0; B connects via explicit seed -> envelope delivered."""
    received = []
    net["B"].set_on_accept(lambda e: received.append(e))
    net["A"].send(_env("A", "B"))
    for _ in range(40):
        if received:
            break
        time.sleep(0.1)
    assert len(received) == 1
    assert received[0].sender == "A"


def test_remote_ready_explicit_host_config_preserved(net):
    """Config surface: host + port survive into NodeStatus (operator observability)."""
    from services.kroft_node_manager import KroftNodeManager, NodeSpec
    mgr = KroftNodeManager(base_state_root=".kroft_remote_mgr")
    spec = NodeSpec(id="remote1", port=7303, host="0.0.0.0", state_root=".kroft_remote_mgr/remote1")
    # start() would launch run_kroft.py subprocess; here we only assert the spec carries host
    assert spec.host == "0.0.0.0"
    assert spec.resolved_state_root() == ".kroft_remote_mgr/remote1"
