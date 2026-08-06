"""ТЗ-FED-REPL-01 (ADR-094) — Federation replication of signed SkillPackages, K8 tests (Флаг 1b).

Covers: package A->B via INetworkTransport, B verifies + installs; untrusted author -> rejected;
tampered payload -> rejected; version supersede between nodes; determinism (I-09). K5: reuses
INetworkTransport.send_soft_layer/on_soft_layer (NW-01), SkillPackage/ISkillRepository
(MARKETPLACE-01), ITrustRegistry (IDT-01) — no transport/signature/trust port duplicated.
Existing FED/MARKETPLACE/IDT tests intact (run separately).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import pytest

from adapters.hmac_signer import HmacSigner
from contracts.i_identity import TrustMeta
from contracts.i_marketplace import SkillPackage
from contracts.i_memory import Procedure
from kernel.identity import ReferenceTrustRegistry
from services.skill_distributor import SkillDistributor
from services.skill_marketplace import SkillPackager, SkillRepository


# ---- in-process loopback transport (tests only) ------------------------------
@dataclass
class _Bus:
    members: List["InMemoryNetworkTransport"] = field(default_factory=list)


class InMemoryNetworkTransport:
    """Loopback INetworkTransport for federation tests (ships soft-layer between nodes)."""

    def __init__(self, bus: _Bus) -> None:
        self._bus = bus
        self._node_id: Optional[str] = None
        self._soft_handlers: List[Callable] = []
        if self not in self._bus.members:
            self._bus.members.append(self)  # loopback auto-join

    def connect(self, node_id: str, peers: List[str]) -> None:
        self._node_id = node_id
        if self not in self._bus.members:
            self._bus.members.append(self)

    def send_event(self, event) -> None:  # pragma: no cover - not used here
        raise NotImplementedError

    def send_facts(self, facts: List[dict], sender_node_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def on_event(self, handler) -> None:  # pragma: no cover
        raise NotImplementedError

    def on_facts(self, handler) -> None:  # pragma: no cover
        raise NotImplementedError

    def send_soft_layer(self, items: List[dict], sender_node_id: str) -> None:
        for m in self._bus.members:
            if m is self:
                continue
            for h in m._soft_handlers:
                h(items, sender_node_id)

    def on_soft_layer(self, handler: Callable) -> None:
        self._soft_handlers.append(handler)

    def disconnect(self) -> None:
        if self in self._bus.members:
            self._bus.members.remove(self)


# ---- fixtures ---------------------------------------------------------------
def _signer():
    return HmacSigner(b"kroft-shared-secret")


def _procedure(version=1, steps=("echo good",)):
    return Procedure(skill_id=f"cap.v{version}", name="cap", capability="cap",
                     steps=steps, version=version, confidence=0.9)


def _trusted_alice() -> ReferenceTrustRegistry:
    t = ReferenceTrustRegistry()
    t.record(TrustMeta(item_id="alice-cap", trust_score=0.9, version=1, author_id="alice"))
    return t


# 1) implements port
def test_distributor_implements_port():
    from contracts.i_skill_distributor import ISkillDistributor
    repo = SkillRepository(_signer())
    assert isinstance(SkillDistributor("nodeA", repo), ISkillDistributor)


# 2) package A -> B via network, B verifies + installs
def test_replicate_a_to_b_installs():
    bus = _Bus()
    signer = _signer()
    repo_a = SkillRepository(signer)
    repo_b = SkillRepository(signer)
    dist_a = SkillDistributor("nodeA", repo_a, InMemoryNetworkTransport(bus))
    dist_b = SkillDistributor("nodeB", repo_b, InMemoryNetworkTransport(bus),
                              trust_registry=_trusted_alice())
    pkg = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    dist_a.publish_remote(pkg, dist_a._transport)
    assert "cap" in repo_b._installed
    assert repo_b._installed["cap"].version == 1


# 3) untrusted author -> B rejects (O1)
def test_replicate_untrusted_rejected():
    bus = _Bus()
    signer = _signer()
    repo_a = SkillRepository(signer)
    repo_b = SkillRepository(signer)
    dist_a = SkillDistributor("nodeA", repo_a, InMemoryNetworkTransport(bus))
    # B has an EMPTY trust registry (mallory never recorded -> trust 0.0)
    dist_b = SkillDistributor("nodeB", repo_b, InMemoryNetworkTransport(bus),
                              trust_registry=ReferenceTrustRegistry())
    pkg = SkillPackager.package(_procedure(), author="mallory", signer=signer, version=1)
    dist_a.publish_remote(pkg, dist_a._transport)
    assert "cap" not in repo_b._installed


# 4) tampered payload -> B rejects (O1)
def test_replicate_tampered_rejected():
    bus = _Bus()
    signer = _signer()
    repo_a = SkillRepository(signer)
    repo_b = SkillRepository(signer)
    dist_a = SkillDistributor("nodeA", repo_a, InMemoryNetworkTransport(bus))
    dist_b = SkillDistributor("nodeB", repo_b, InMemoryNetworkTransport(bus),
                              trust_registry=_trusted_alice())
    pkg = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    # tamper AFTER signing
    tampered = pkg.__class__(**{**pkg.__dict__, "payload": {**pkg.payload, "steps": ["echo hacked"]}})
    dist_a.publish_remote(tampered, dist_a._transport)
    assert "cap" not in repo_b._installed


# 5) version supersede between nodes
def test_replicate_version_supersede():
    bus = _Bus()
    signer = _signer()
    repo_b = SkillRepository(signer)
    dist_a = SkillDistributor("nodeA", SkillRepository(signer), InMemoryNetworkTransport(bus))
    dist_b = SkillDistributor("nodeB", repo_b, InMemoryNetworkTransport(bus),
                              trust_registry=_trusted_alice())
    v1 = SkillPackager.package(_procedure(version=1), author="alice", signer=signer, version=1)
    v2 = SkillPackager.package(_procedure(version=2, steps=("echo better",)),
                                author="alice", signer=signer, version=2)
    dist_a.publish_remote(v1, dist_a._transport)
    dist_a.publish_remote(v2, dist_a._transport)
    assert repo_b._installed["cap"].version == 2
    assert len(repo_b.superseded("cap")) == 1
    assert repo_b.superseded("cap")[0].version == 1


# 6) determinism (I-09)
def test_determinism():
    signer = _signer()
    a = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    b = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    assert a.signature == b.signature
    assert a.id == b.id
