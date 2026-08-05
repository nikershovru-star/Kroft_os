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
from contracts.i_identity import AgentIdentity
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
from kernel.agent_executor import build_agent_executor


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
    agent_executor=None,
    identity_registry=None,
    plugin_registry=None,
    action_log=None,
) -> Tuple[FederatedNode, NetworkTransport]:
    """One federated node over REAL localhost TCP.

    Builds a real NetworkTransport, connects to peers, then wraps it in the transport-agnostic
    build_federated_node (Флаг 1 fix 321fc21). Returns (FederatedNode, transport) so the caller
    can ensure_connected() + disconnect() for deterministic barriers / clean teardown.

    ТЗ-NET-AGENT-EXEC-01 (commit 3, integration): optional `agent_executor` + регистровые
    deps (`identity_registry`/`plugin_registry`/`action_log`) — когда заданы, узел строится
    через build_federated_node(..., orchestrator=None, agent_executor=...) и его ЛОКАЛЬНЫЙ
    orchestrator исполняет agent-routed цели РЕАЛЬНЫМ agent tick'ом (reuse ТЗ-AGENT-EXEC-01).
    Без agent_executor — прежнее поведение (передаётся готовый orchestrator). Backward-compat.
    """
    t = NetworkTransport(node_id, port)
    if peer_addrs:
        t.connect(node_id, peer_addrs)
    if agent_executor is not None:
        # Build the node WITH a real agent executor on the server side (ТЗ-NET-AGENT-EXEC-01).
        node = build_federated_node(
            t, None, trust, node_id,
            trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=remote_nodes,
            agent_executor=agent_executor,
            identity_registry=identity_registry, plugin_registry=plugin_registry,
            action_log=action_log,
        )
    else:
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
    agent_executor=None,
    agent_capability: Optional[str] = None,
) -> Tuple[FederatedNode, FederatedNode, ReferenceTrustRegistry, ReferenceTrustRegistry, NetworkTransport, NetworkTransport]:
    """Two federated nodes A and B over REAL localhost TCP, wired for dispatch.

    A holds (plugin for A, trust seeded A=0.9, B=0.9); B likewise. Each node is client+server
    sharing one orchestrator+trust+transport. `b_fail` makes B's plugin return failure (to test
    trust-lowering from a real failed remote outcome). Returns (nodeA, nodeB, trustA, trustB, tA, tB).
    Caller must call ensure_connected() on both transports before dispatch (determinism).

    ТЗ-NET-AGENT-EXEC-01 (commit 3, integration): when `agent_executor` + `agent_capability`
    are given, node B also registers a local AGENT with that specialization (trust>=local
    threshold) and builds its orchestrator WITH the real agent executor. Then a goal whose
    capability == `agent_capability`, addressed to B, is executed by B's REAL agent tick
    (ReferenceAgentExecutor) and the real outcome travels back over the socket to A — closing
    the loop (ТЗ-AGENT-EXEC-01 over the network). Without `agent_executor`, behaviour is unchanged
    (B executes via plugin / delegated) — backward-compat.
    """
    pa, pb = _next_port(), _next_port()
    addr_a, addr_b = f"127.0.0.1:{pa}", f"127.0.0.1:{pb}"

    # Node A (client that dispatches to B)
    plA = ReferencePluginRegistry()
    plA.register(plugin_factory(True))
    trustA = ReferenceTrustRegistry()
    trustA.seed("A", seed_trust)
    trustA.seed("B", seed_trust)
    idsA = ReferenceIdentityRegistry()
    idsA.register(AgentIdentity(agent_id="A", specialization=("noop",), trust_level=seed_trust))
    orchA = build_orchestrator(
        idsA, plA, trustA, ReferenceActionLog(), trust_threshold=0.0
    )
    nodeA, tA = build_tcp_federated_node(
        "A", pa, [addr_b], orchA, trustA,
        trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=("B",),
    )

    # Node B (executes goals addressed to it). Optionally a REAL agent executor.
    plB = ReferencePluginRegistry()
    plB.register(plugin_factory(not b_fail))
    trustB = ReferenceTrustRegistry()
    trustB.seed("A", seed_trust)
    trustB.seed("B", seed_trust)
    idsB = ReferenceIdentityRegistry()
    if agent_capability is not None:
        # Register a local agent on B whose specialization matches the agent capability, so
        # B's route() selects the agent path when an agent-goal arrives. Trust seeded >= local
        # threshold (0.0) so it is eligible.
        idsB.register(AgentIdentity(
            agent_id="B-agent", specialization=(agent_capability,), trust_level=seed_trust))
    if agent_executor is not None:
        orchB = build_orchestrator(
            idsB, plB, trustB, ReferenceActionLog(), trust_threshold=0.0,
            agent_executor=agent_executor,
        )
        nodeB, tB = build_tcp_federated_node(
            "B", pb, [addr_a], None, trustB,
            trust_threshold=trust_threshold, trust_delta=trust_delta, remote_nodes=("A",),
            agent_executor=agent_executor, identity_registry=idsB,
            plugin_registry=plB, action_log=ReferenceActionLog(),
        )
    else:
        orchB = build_orchestrator(
            idsB, plB, trustB, ReferenceActionLog(), trust_threshold=0.0
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
