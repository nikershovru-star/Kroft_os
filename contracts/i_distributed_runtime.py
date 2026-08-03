"""Distributed Runtime ports — TZ-015 (ADR-044, RFC-015).

K1-compliant: stdlib + contracts ONLY. Reuses WP-14 substrates through their PORTS
(IDistributedEventBus, ICrdtGraph, ILeaderElector) — never imports concrete adapters
directly (K6). Cognitive contracts (IWorldState, CausalMark, ConfidenceScore) are the
federation-safe substrate extended by gate C.

Components (per TZ-015):
- INodeDiscovery       (gossip/SWIM membership)
- IClusterRegistry      (node -> addr map, CRDT-backed)
- IRemoteAgentExecutor  (agent execution on remote node via msg-pass)
- ISharedContext        (federated projection of WorldState, causal-merge)
- INetworkSupervisor     (leader-failover orchestration)
- IClusterMetrics        (reuse ITelemetrySink)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from contracts.cognitive_domain import CausalMark, ConfidenceScore, WorldState
from contracts.i_agent_platform import IAgentPlatform
from contracts.i_crdt_graph import ICrdtGraph
from contracts.i_distributed_event_bus import IDistributedEventBus
from contracts.i_leader_elector import ILeaderElector
from contracts.i_network_transport import INetworkTransport
from contracts.i_telemetry import ITelemetrySink


# --------------------------------------------------------------------------
# Node Discovery (gossip/SWIM)
# --------------------------------------------------------------------------
class INodeDiscovery(ABC):
    """Probabilistic membership + failure detection (SWIM/gossip)."""

    @abstractmethod
    def start(self, self_id: str, seed_peers: List[str]) -> None: ...

    @abstractmethod
    def members(self) -> List[str]: ...

    @abstractmethod
    def is_alive(self, node_id: str) -> bool: ...


# --------------------------------------------------------------------------
# Cluster Registry (node -> addr, CRDT-backed)
# --------------------------------------------------------------------------
class IClusterRegistry(ABC):
    """Node directory; backed by ICrdtGraph so it converges across nodes."""

    @abstractmethod
    def register(self, node_id: str, addr: str) -> None: ...

    @abstractmethod
    def lookup(self, node_id: str) -> Optional[str]: ...

    @abstractmethod
    def all(self) -> Dict[str, str]: ...


# --------------------------------------------------------------------------
# Remote Agent Executor (msg-pass)
# --------------------------------------------------------------------------
class IRemoteAgentExecutor(ABC):
    """Execute a goal on a remote node via IAgentPlatform; returns result payload."""

    @abstractmethod
    def submit_remote(self, node_id: str, goal: str,
                      platform: IAgentPlatform) -> str: ...


# --------------------------------------------------------------------------
# Shared Context (federated projection of WorldState) — gate C
# --------------------------------------------------------------------------
class ISharedContext(ABC):
    """Federated projection of local WorldState (ADR-054 I-08). Selective by default.

    Merge is CAUSAL: facts carry CausalMark (node_origin+seq), so replicas converge
    without trusting wall-clock time. Selective sharing: only granted scopes sync.
    """

    @abstractmethod
    def publish_selective(self, world: WorldState, scope: str) -> List[dict]: ...

    @abstractmethod
    def merge_remote(self, remote_facts: List[dict],
                     remote_marks: Dict[str, CausalMark]) -> WorldState: ...

    def replicate_to(self, transport: "INetworkTransport", scope: str,
                     world: WorldState) -> None:
        """ТЗ-NW-01: real-network replication. Publish selective facts and ship them
        over the transport (wire lamport) to peers. Receiver runs merge_remote on
        arrival. Default impl raises (subclass must wire transport); kept non-abstract
        so TZ-015 in-process usage is unaffected.
        """
        raise NotImplementedError("replicate_to requires a NetworkFederationService")


# --------------------------------------------------------------------------
# Network Supervisor (leader-failover orchestration)
# --------------------------------------------------------------------------
class INetworkSupervisor(ABC):
    """Drives node failover using ILeaderElector + recovery (reuse WP-14)."""

    @abstractmethod
    def supervise(self, elector: ILeaderElector, bus: IDistributedEventBus) -> None: ...


# --------------------------------------------------------------------------
# Cluster Metrics (reuse ITelemetrySink)
# --------------------------------------------------------------------------
class IClusterMetrics(ABC):
    """Cluster-level telemetry; reuses ITelemetrySink (TZ-OBS-001)."""

    @abstractmethod
    def emit_node_metric(self, node_id: str, name: str, value: float,
                         confidence: ConfidenceScore, sink: ITelemetrySink) -> None: ...
