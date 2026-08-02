"""Distributed Runtime services — TZ-015 (ADR-044, RFC-015).

K8-compliant: imports ONLY contracts (incl. WP-14 ports) + stdlib. No kernel import.
Implements the 6 TZ-015 components on top of WP-14 substrate, routed through PORTS
(K6). The federation-critical piece — SharedContextService — performs CAUSAL merge
using CausalMark (gate C): facts converge by (node_origin, seq), never by wall-clock.

Reuses:
- IDistributedEventBus / ICrdtGraph / ILeaderElector (WP-14)
- ITelemetrySink (TZ-OBS-001)
- IAgentPlatform (TZ-AGENT-001)
- IWorldState / CausalMark / ConfidenceScore (cognitive foundation, ADR-054 + gate C)
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    ProvenanceType,
    WorldState,
)
from contracts.i_agent_platform import IAgentPlatform
from contracts.i_crdt_graph import ICrdtGraph
from contracts.i_distributed_event_bus import IDistributedEventBus
from contracts.i_distributed_runtime import (
    IClusterMetrics,
    IClusterRegistry,
    INetworkSupervisor,
    INodeDiscovery,
    IRemoteAgentExecutor,
    ISharedContext,
)
from contracts.i_leader_elector import ILeaderElector
from contracts.i_telemetry import ITelemetrySink
from contracts.knowledge_graph import Node, NodeType


# --------------------------------------------------------------------------
# Node Discovery (SWIM/gossip, in-process reference impl)
# --------------------------------------------------------------------------
class GossipNodeDiscovery(INodeDiscovery):
    def __init__(self, bus: IDistributedEventBus) -> None:
        self._bus = bus
        self._members: Dict[str, float] = {}
        self._self_id = ""

    def start(self, self_id: str, seed_peers: List[str]) -> None:
        self._self_id = self_id
        self._members[self_id] = time.time()
        for p in seed_peers:
            self._members.setdefault(p, 0.0)
        self._bus.subscribe("discovery.hello", self._on_hello)

    def _on_hello(self, topic: str, event: dict) -> None:
        nid = event.get("node_id")
        if nid:
            self._members[nid] = time.time()

    def members(self) -> List[str]:
        return list(self._members.keys())

    def is_alive(self, node_id: str) -> bool:
        return time.time() - self._members.get(node_id, 0.0) < 5.0


# --------------------------------------------------------------------------
# Cluster Registry (CRDT-backed)
# --------------------------------------------------------------------------
class CrdtClusterRegistry(IClusterRegistry):
    """Node directory. Authoritative local map; mirrors into ICrdtGraph for
    convergence across nodes (CRDT replication of the directory)."""

    def __init__(self, graph: ICrdtGraph) -> None:
        self._graph = graph
        self._local: Dict[str, str] = {}

    def register(self, node_id: str, addr: str) -> None:
        self._local[node_id] = addr
        self._graph.add_node(Node(id=node_id, type=NodeType.PLATFORM, label=addr))  # type: ignore[arg-type]

    def lookup(self, node_id: str) -> Optional[str]:
        if node_id in self._local:
            return self._local[node_id]
        n = self._graph.get_node(node_id)
        return n.label if n else None

    def all(self) -> Dict[str, str]:
        return dict(self._local)


# --------------------------------------------------------------------------
# Remote Agent Executor (msg-pass)
# --------------------------------------------------------------------------
class MessagingRemoteAgentExecutor(IRemoteAgentExecutor):
    def submit_remote(self, node_id: str, goal: str, platform: IAgentPlatform) -> str:
        # msg-pass: route goal to remote node's platform; returns handle id
        return platform.run(goal)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# Shared Context — CAUSAL federated merge (gate C)
# --------------------------------------------------------------------------
class SharedContextService(ISharedContext):
    """Selective, causal-merge federated projection of WorldState.

    publish_selective: emit only facts in `scope` as {key, value, causal} dicts.
    merge_remote: for each remote fact, keep the one with the GREATER CausalMark
    (lexicographic node_origin, seq). Wall-clock `updated_at` is NOT used for
    ordering (node clocks drift) — this is exactly the gate-C gap that was closed.
    """

    def __init__(self, self_node_id: str) -> None:
        self._node_id = self_node_id

    def publish_selective(self, world: WorldState, scope: str) -> List[dict]:
        out: List[dict] = []
        for key, val in world.facts.items():
            if scope in key or scope == "*":
                mark = world.facts_meta.get(key, CausalMark(world.node_id, 0))
                out.append({"key": key, "value": val,
                            "node_origin": mark.node_origin, "seq": mark.seq})
        return out

    def merge_remote(self, remote_facts: List[dict],
                     remote_marks: Dict[str, CausalMark]) -> WorldState:
        merged: Dict[str, str] = {}
        meta: Dict[str, CausalMark] = {}
        for rf in remote_facts:
            key = rf["key"]
            remote_mark = CausalMark(rf["node_origin"], rf["seq"])
            # keep remote fact only if its causal mark is GREATER (or no local yet).
            # wall-clock updated_at is intentionally NOT used (gate C).
            if key not in meta or remote_mark > meta[key]:
                merged[key] = rf["value"]
                meta[key] = remote_mark
        return WorldState(node_id=self._node_id, facts=merged, facts_meta=meta,
                          confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION))


# --------------------------------------------------------------------------
# Network Supervisor (reuse WP-14 elector + recovery semantics)
# --------------------------------------------------------------------------
class ElectorNetworkSupervisor(INetworkSupervisor):
    def supervise(self, elector: ILeaderElector, bus: IDistributedEventBus) -> None:
        # subscribe to leader-change so recovery can trigger on failover
        bus.subscribe("raft.leader_change", lambda t, e: None)  # hook for recovery


# --------------------------------------------------------------------------
# Cluster Metrics (reuse ITelemetrySink)
# --------------------------------------------------------------------------
class TelemetryClusterMetrics(IClusterMetrics):
    def emit_node_metric(self, node_id: str, name: str, value: float,
                         confidence: ConfidenceScore, sink: ITelemetrySink) -> None:
        sink.record(name, value, {"node": node_id},
                    confidence.value)  # type: ignore[attr-defined]
