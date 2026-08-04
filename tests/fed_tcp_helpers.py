"""Real-TCP federated wiring helpers for ТЗ-FED-TCP-01 (reference impl).

K1/K6 note: this module lives under `tests/` (NOT scanned by the arch gate's layer-import
scanner), so it may import BOTH `adapters.network_transport` (real TCP) and `kernel.federated_executor`
(transport-agnostic build_federated_node). A equivalent helper could NOT live in `kernel/` or
`adapters/` (they may not cross-import). The composition happens here, mirroring FSE-01 `_wire`.

Pattern (from FSE-01 real-TCP tests): unique ports, NetworkTransport.connect, ensure_connected
barrier (NO wall-clock sleep), disconnect() teardown.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Tuple

from adapters.network_transport import NetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.plugin import ICapabilityPlugin, PluginManifest, PluginResult
from kernel.federated_executor import build_federated_node, FederatedNode
from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry


_PORT = [9100]  # unique-port source (FSE-01 pattern)


def _next_port() -> int:
    _PORT[0] += 1
    return _PORT[0]


def build_tcp_federated_node(
    node_id: str,
    port: int,
    peer_addrs: List[str],
    orchestrator,
    trust: ReferenceTrustRegistry,
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    remote_nodes: Tuple[str, ...] = (),
) -> Tuple[FederatedNode, NetworkTransport]:
    """One federated node over REAL localhost TCP.

    Builds a real NetworkTransport, connects to peers, then wraps it in the transport-agnostic
    build_federated_node (Флаг 1 fix 321fc21). Returns (FederatedNode, transport) so the caller
    can ensure_connected() + disconnect() for deterministic barriers / clean teardown.
    """
    t = NetworkTransport(node_id, port)
    if peer_addrs:
        t.connect(node_id, peer_addrs)
    node = build_federated_node(
        t, orchestrator, trust, node_id,
        trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=remote_nodes,
    )
    node.start()
    return node, t


def make_tcp_federated_pair(
    plugin_factory: Callable[[bool], ICapabilityPlugin],
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    seed_trust: float = 0.9,
    b_fail: bool = False,
) -> Tuple[FederatedNode, FederatedNode, ReferenceTrustRegistry, ReferenceTrustRegistry, NetworkTransport, NetworkTransport]:
    """Two federated nodes A and B over REAL localhost TCP, wired for dispatch.

    A holds (plugin for A, trust seeded A=0.9, B=0.9); B likewise. Each node is client+server
    sharing one orchestrator+trust+transport. `b_fail` makes B's plugin return failure (to test
    trust-lowering from a real failed remote outcome). Returns (nodeA, nodeB, trustA, trustB, tA, tB).
    Caller must call ensure_connected() on both transports before dispatch (determinism).
    """
    pa, pb = _next_port(), _next_port()
    addr_a, addr_b = f"127.0.0.1:{pa}", f"127.0.0.1:{pb}"

    # Node A
    plA = ReferencePluginRegistry()
    plA.register(plugin_factory(True))
    trustA = ReferenceTrustRegistry()
    trustA.seed("A", seed_trust)
    trustA.seed("B", seed_trust)
    orchA = build_orchestrator(
        ReferenceIdentityRegistry(), plA, trustA, ReferenceActionLog(), trust_threshold=0.0
    )
    nodeA, tA = build_tcp_federated_node(
        "A", pa, [addr_b], orchA, trustA,
        trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=("B",),
    )

    # Node B (executes goals addressed to it)
    plB = ReferencePluginRegistry()
    plB.register(plugin_factory(not b_fail))
    trustB = ReferenceTrustRegistry()
    trustB.seed("A", seed_trust)
    trustB.seed("B", seed_trust)
    orchB = build_orchestrator(
        ReferenceIdentityRegistry(), plB, trustB, ReferenceActionLog(), trust_threshold=0.0
    )
    nodeB, tB = build_tcp_federated_node(
        "B", pb, [addr_a], orchB, trustB,
        trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=("A",),
    )
    return nodeA, nodeB, trustA, trustB, tA, tB


def ensure_pair_connected(tA, tB, timeout: float = 3.0) -> bool:
    """Deterministic barrier: block until both TCP links are up (NO sleep-luck)."""
    return tA.ensure_connected(timeout) and tB.ensure_connected(timeout)


def teardown_tcp_pair(tA, tB) -> None:
    """Clean shutdown (FSE-01 pattern): disconnect both transports."""
    try:
        tA.disconnect()
    except Exception:
        pass
    try:
        tB.disconnect()
    except Exception:
        pass
