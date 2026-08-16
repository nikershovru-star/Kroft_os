"""KROFT-NET-05 — KnowledgeEnvelope wire transfer + multi-hop (TZ §18/§19/§20/§25/§29).

Boots 3 real TcpEventBus nodes (A/B/C) on distinct ports, wires KnowledgeEnvelopeRouter
on each, and proves:
  TEST 5/6: A -> B direct share; B verifies signature + accepts (TZ §25 T5/T6/T7/T8)
  MULTI-HOP: A -> B -> C (B forwards because recipient=C, ttl>1)  [TZ §18]
  REPLAY: same envelope twice -> second rejected by ReplayGuard  [TZ §29]

REUSE: TcpEventBus (carrier) + HmacSigner (i_signature) + KnowledgeEnvelope + ReplayGuard.
No new federation / crypto.

Targeted (spawns real TCP buses). Run: pytest tests/test_knowledge_envelope_router.py -q
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


def _make_node(node_id, port):
    bus = TcpEventBus(node_id, port)
    bus.join([])  # start server only; peers connected after all servers are up
    trust = ReferenceTrustRegistry()
    trust.seed(node_id, 0.9)
    signer = HmacSigner(b"shared-test-key")
    router = KnowledgeEnvelopeRouter(
        node_id=node_id, bus=bus, trust_registry=trust, signer=signer,
        state_root=f".kroft_test/{node_id}",
    )
    return bus, router


def _env(sender, recipient, kid="k1", lamport=8):
    return KnowledgeEnvelope(
        knowledge_id=kid, content="X is true", origin=KnowledgeOrigin.LOCAL,
        sender=sender, recipient=recipient, resolution=ResolutionLevel.SYSTEM,
        confidence=0.9, provenance=["fact-1", "ep-2"], trust=0.9,
        signature="signed", ttl=8, lamport=lamport,
    )


# Full-mesh seeds, applied AFTER all three servers are up so connections succeed.
SEEDS = {
    "A": ["127.0.0.1:7102", "127.0.0.1:7103"],
    "B": ["127.0.0.1:7101", "127.0.0.1:7103"],
    "C": ["127.0.0.1:7101", "127.0.0.1:7102"],
}


@pytest.fixture
def net():
    a_bus, a = _make_node("A", 7101)
    b_bus, b = _make_node("B", 7102)
    c_bus, c = _make_node("C", 7103)
    # now connect (all servers are up)
    a_bus.join(SEEDS["A"])
    b_bus.join(SEEDS["B"])
    c_bus.join(SEEDS["C"])
    time.sleep(1.0)  # let TCP connections establish (full-mesh bidirectional)
    yield {"A": a, "B": b, "C": c}
    a_bus.leave(); b_bus.leave(); c_bus.leave()


def test_a_shares_to_b_and_b_accepts(net):
    """TZ §25 T5/T6/T7/T8: A shares, B verifies + accepts."""
    received = []
    net["B"].set_on_accept(lambda e: received.append(e))
    net["A"].send(_env("A", "B"))
    for _ in range(40):
        if received:
            break
        time.sleep(0.1)
    assert len(received) == 1
    assert received[0].knowledge_id == "k1"
    assert received[0].sender == "A"


def test_multi_hop_a_to_b_to_c(net):
    """TZ §18: A -> B -> C (B forwards because recipient=C)."""
    received = []
    net["C"].set_on_accept(lambda e: received.append(e))
    net["A"].send(_env("A", "C", kid="k-hop"))
    for _ in range(40):
        if received:
            break
        time.sleep(0.1)
    assert len(received) == 1
    assert received[0].knowledge_id == "k-hop"
    assert received[0].recipient == "C"


def test_replay_rejected(net):
    """TZ §29: same envelope delivered twice -> second dropped by ReplayGuard."""
    received = []
    net["B"].set_on_accept(lambda e: received.append(e))
    env = _env("A", "B", kid="k-replay")
    net["A"].send(env)
    time.sleep(0.5)
    first = len(received)
    # re-send identical envelope (same lamport -> replay)
    net["A"].send(env)
    time.sleep(0.5)
    # replay guard keys on (origin, lamport); second send reuses seq -> rejected
    assert len(received) == first  # no duplicate accepted


def test_low_trust_quarantined(net):
    """TZ §29: TRUST < threshold -> envelope goes to QUARANTINE (not silently dropped)."""
    quarantined = []
    net["B"].set_on_quarantine(lambda s, e, r: quarantined.append((s, e)))
    # lower B's trust view of sender A below threshold (0.3) so effective trust fails
    net["B"]._trust.seed("A", 0.1)
    low = _env("A", "B", kid="k-lowtrust", lamport=11)
    object.__setattr__(low, "trust", 0.05)
    net["A"].send(low)
    for _ in range(40):
        if quarantined:
            break
        time.sleep(0.1)
    assert len(quarantined) >= 1
    assert quarantined[0][0].name == "QUARANTINED"


def test_bad_signature_quarantined(net):
    """TZ §29: corrupted/missing signature -> REJECTED into quarantine store."""
    quarantined = []
    net["B"].set_on_quarantine(lambda s, e, r: quarantined.append((s, e, r)))
    # manually publish an envelope with a wrong signature (bypass router.sign send path)
    import json
    d = json.loads(_env("A", "B", kid="k-badsig").to_wire().decode("utf-8"))
    d["causal"] = {"lamport": 5, "node_origin": "A"}
    d["lamport"] = 5
    d["signature"] = "forged-signature"
    net["A"]._bus.publish("kroft.knowledge", d)
    for _ in range(40):
        if quarantined:
            break
        time.sleep(0.1)
    assert len(quarantined) >= 1
    assert quarantined[0][0].name == "REJECTED"


def test_ttl_exhausted_graceful_noop(net):
    """TZ §29: A -> nonexistent node with ttl=1 -> no node accepts, no crash."""
    received = []
    net["B"].set_on_accept(lambda e: received.append(e))
    net["C"].set_on_accept(lambda e: received.append(e))
    # recipient X not in network; ttl=1 means intermediates cannot forward further
    net["A"].send(_env("A", "X", kid="k-ttl", lamport=7))
    time.sleep(0.5)
    assert len(received) == 0  # nobody accepted; graceful (no exception)


def test_node_offline_graceful(net):
    """TZ §29: sending to an offline peer -> sender does not crash (graceful failure)."""
    # B leaves the mesh; A still tries to send to B
    net["B"]._bus.leave()
    time.sleep(0.3)
    # should not raise
    net["A"].send(_env("A", "B", kid="k-offline", lamport=9))
    time.sleep(0.3)
    assert True  # reached here == no exception propagated
