"""Distributed capstone composition — end-to-end self-evolution across nodes (ТЗ-CAPSTONE-02, ADR-095).

K5: this is PURE COMPOSITION over already-shipped components — NO new contract/port. Reuses:
  - services/skill_evolution.py      SkillEvolver        (EVOLUTION-01) — propose + sandbox-test + version
  - services/skill_marketplace.py    SkillPackager / SkillRepository (MARKETPLACE-01) — sign + install
  - services/skill_distributor.py    SkillDistributor    (FED-REPL-01)  — replicate signed pkg via network
  - contracts/i_network_transport.py INetworkTransport   (NW-01)        — reused (loopback impl here)
  - contracts/i_identity.py          ITrustRegistry      (IDT-01)       — trust gate
  - contracts/i_signature.py          ISignatureProvider  (CRYPTO-01)    — HMAC signer
  - adapters/subprocess_sandbox.py    SubprocessSandbox   (ADR-039)      — injected into SkillEvolver
  - services/memory_platform.py       InMemoryProceduralMemory            — injected into SkillEvolver
The capstone proves the JOINT behavior: node A improves a skill (SkillEvolver) -> packages it
(SkillPackager) -> replicates to B (SkillDistributor) -> B verifies + trust-gates + installs
(SkillRepository) -> B's BEHAVIOR changes from the improved skill.

Флаг C: composition only — NOT wired into build_kernel. Composition root may import services +
adapters + kernel (gate rule: composition -> everything); the composed parts stay axis-clean.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from adapters.hmac_signer import HmacSigner
from adapters.subprocess_sandbox import SubprocessSandbox
from contracts.i_identity import ITrustRegistry, TrustMeta
from contracts.i_marketplace import SkillPackage
from contracts.i_memory import Procedure
from contracts.i_network_transport import INetworkTransport
from kernel.identity import ReferenceTrustRegistry
from services.memory_platform import InMemoryProceduralMemory
from services.skill_distributor import SkillDistributor
from services.skill_evolution import SkillEvolver
from services.skill_marketplace import SkillPackager, SkillRepository
from contracts.i_skill_evolver import SkillUsageStats


# ---- in-process loopback transport (composition-scoped, reused by both nodes) ----
class _Bus:
    def __init__(self) -> None:
        self.members: List["LoopbackTransport"] = []


class LoopbackTransport(INetworkTransport):
    """In-process INetworkTransport for the capstone (ships soft-layer between the two nodes)."""

    def __init__(self, bus: _Bus) -> None:
        self._bus = bus
        self._node_id: Optional[str] = None
        self._soft_handlers: List[Callable] = []
        if self not in self._bus.members:
            self._bus.members.append(self)

    def connect(self, node_id: str, peers: List[str]) -> None:
        self._node_id = node_id

    def send_event(self, event) -> None:  # pragma: no cover - unused here
        raise NotImplementedError

    def send_facts(self, facts: List[dict], sender_node_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def on_event(self, handler: Callable) -> None:  # pragma: no cover
        raise NotImplementedError

    def on_facts(self, handler: Callable) -> None:  # pragma: no cover
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


class DistributedNode:
    """One KROFT node composed from SkillEvolver + SkillRepository + SkillDistributor + trust.

    A node can (sender side) evolve a skill and publish the improved, signed package; and
    (receiver side) install incoming packages and USE the installed skill (behavior).
    """

    def __init__(self, node_id: str, author: str, signer, transport: INetworkTransport,
                 trust_registry: ITrustRegistry, sandbox: SubprocessSandbox,
                 memory: InMemoryProceduralMemory,
                 min_uses: int = 5, success_threshold: float = 0.8) -> None:
        self.node_id = node_id
        self.author = author
        self.signer = signer
        self.transport = transport
        self._sandbox = sandbox
        self.evolver = SkillEvolver(sandbox, memory, min_uses=min_uses,
                                   success_threshold=success_threshold)
        self.repo = SkillRepository(signer)
        self.dist = SkillDistributor(node_id, self.repo, transport, trust_registry)

    # --- sender side: improve -> package -> replicate ---
    def evolve_and_publish(self, skill: Procedure, stats: SkillUsageStats) -> Procedure:
        """Improve a skill (SkillEvolver), sign+package it, and replicate to peers."""
        evolved = self.evolver.evolve_skill(skill, stats)
        pkg = SkillPackager.package(evolved, author=self.author, signer=self.signer,
                                    version=evolved.version)
        self.dist.publish_remote(pkg, self.transport)
        return evolved

    # --- receiver side: use the installed (replicated) skill -> behavior ---
    def use_skill(self, name: str) -> Optional[float]:
        """Execute the installed skill's steps in the sandbox; return its success rate (behavior).

        Before replication the skill is unknown -> None. After replication from A, the improved
        skill is installed and its (better) behavior is observable here on B.
        """
        proc = self.repo._installed.get(name)
        if proc is None:
            return None
        passed = total = 0
        for step in proc.steps:
            total += 1
            try:
                res = self._sandbox.execute(step.split(), timeout_sec=5.0, label=name)
                if res.returncode == 0 and not res.killed:
                    passed += 1
            except Exception:
                pass
        return (passed / float(total)) if total else 0.0


def build_distributed_capstone(author: str = "alice",
                               signer_key: bytes = b"kroft-shared-secret",
                               min_uses: int = 5,
                               success_threshold: float = 0.8,
                               trust_score: float = 0.9) -> "tuple[DistributedNode, DistributedNode]":
    """Build two federated nodes (A, B) sharing one signer + trust registry + loopback bus (Флаг C)."""
    bus = _Bus()
    signer = HmacSigner(signer_key)
    trust = ReferenceTrustRegistry()
    trust.record(TrustMeta(item_id=f"{author}-cap", trust_score=trust_score,
                          version=1, author_id=author))
    sandbox = SubprocessSandbox()
    node_a = DistributedNode("nodeA", author, signer, LoopbackTransport(bus), trust,
                             sandbox, InMemoryProceduralMemory(), min_uses, success_threshold)
    node_b = DistributedNode("nodeB", author, signer, LoopbackTransport(bus), trust,
                             sandbox, InMemoryProceduralMemory(), min_uses, success_threshold)
    return node_a, node_b
