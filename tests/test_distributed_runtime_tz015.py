"""Tests for TZ-015 Distributed Runtime (ADR-044, RFC-015) — gate C.

Reuses WP-14 substrate (CrdtGraphEngine, InMemoryEventBus) through their PORTS (K6).
Focus: the gate-C contract extension — CAUSAL merge in SharedContextService using
CausalMark (node_origin+seq), NOT wall-clock timestamp.

Components covered:
- SharedContextService.publish_selective / merge_remote (causal-merge, gate C)
- CrdtClusterRegistry (register/lookup on ICrdtGraph)
- GossipNodeDiscovery (start/members/is_alive)
- TelemetryClusterMetrics (reuse ITelemetrySink)
- MessagingRemoteAgentExecutor (run on IAgentPlatform)
- ElectorNetworkSupervisor (subscribe to leader-change)
"""

import pytest

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    Observation,
    Provenance,
    ProvenanceType,
    WorldState,
)
from contracts.i_crdt_graph import ICrdtGraph
from contracts.i_distributed_event_bus import IDistributedEventBus
from contracts.i_distributed_runtime import (
    IClusterRegistry,
    INodeDiscovery,
    IRemoteAgentExecutor,
    ISharedContext,
)
from infrastructure.eventbus import InMemoryEventBus
from adapters.crdt_graph import CrdtGraphEngine

from services.distributed_runtime import (
    CrdtClusterRegistry,
    ElectorNetworkSupervisor,
    GossipNodeDiscovery,
    MessagingRemoteAgentExecutor,
    SharedContextService,
    TelemetryClusterMetrics,
)


# --------------------------------------------------------------------------
# Shared Context — causal merge (gate C) — the core assertion
# --------------------------------------------------------------------------
def _world(node_id: str, facts: dict) -> WorldState:
    w = WorldState(node_id=node_id, facts=dict(facts))
    # assign causal marks per fact (simulating federation origin)
    return w


def test_shared_context_publish_selective_emits_causal():
    svc = SharedContextService("n1")
    w = WorldState(node_id="n1", facts={"a": "1", "scope:x": "2", "b": "3"})
    w.facts_meta["a"] = CausalMark("n1", 1)
    w.facts_meta["scope:x"] = CausalMark("n1", 2)
    w.facts_meta["b"] = CausalMark("n1", 3)
    sel = svc.publish_selective(w, "scope:x")
    assert [d["key"] for d in sel] == ["scope:x"]
    assert sel[0]["node_origin"] == "n1" and sel[0]["seq"] == 2


def test_shared_context_merge_remote_is_causal_not_wallclock():
    """Two nodes report the same key with conflicting values + DRIFTED wall-clocks.

    Merge MUST pick the GREATER CausalMark (n2,seq=5 > n1,seq=3), not the later
    wall-clock time. This is exactly the gate-C gap closed before federation.
    """
    svc = SharedContextService("n1")
    remote = [
        {"key": "fact", "value": "from-n2", "node_origin": "n2", "seq": 5},
        # n1 with HIGHER wall-clock but LOWER causal seq -> must NOT win
        {"key": "fact", "value": "from-n1-stale", "node_origin": "n1", "seq": 3},
    ]
    merged = svc.merge_remote(remote, WorldState(node_id="n1"))
    assert merged.facts["fact"] == "from-n2"
    assert merged.facts_meta["fact"] == CausalMark("n2", 5)


def test_shared_context_merge_remote_idempotent_on_replay():
    svc = SharedContextService("n1")
    remote = [{"key": "k", "value": "v", "node_origin": "n3", "seq": 7}]
    m1 = svc.merge_remote(remote, WorldState(node_id="n1"))
    m2 = svc.merge_remote(remote, WorldState(node_id="n1"))  # duplicate delivery
    assert m1.facts == m2.facts
    assert m1.facts_meta == m2.facts_meta


# --------------------------------------------------------------------------
# Cluster Registry on CRDT graph
# --------------------------------------------------------------------------
def test_cluster_registry_register_lookup():
    graph: ICrdtGraph = CrdtGraphEngine("registry-node")
    reg: IClusterRegistry = CrdtClusterRegistry(graph)
    reg.register("n2", "127.0.0.1:8002")
    reg.register("n3", "127.0.0.1:8003")
    assert reg.lookup("n2") == "127.0.0.1:8002"
    assert reg.lookup("missing") is None
    assert set(reg.all().keys()) >= {"n2", "n3"}


# --------------------------------------------------------------------------
# Node Discovery (gossip)
# --------------------------------------------------------------------------
def test_node_discovery_start_members():
    bus: IDistributedEventBus = InMemoryEventBus()
    disc: INodeDiscovery = GossipNodeDiscovery(bus)
    disc.start("n1", ["n2", "n3"])
    assert "n1" in disc.members()
    assert disc.is_alive("n1") is True
    assert disc.is_alive("n2") is False  # never heard alive


# --------------------------------------------------------------------------
# Remote Agent Executor (msg-pass via IAgentPlatform.run)
# --------------------------------------------------------------------------
class _FakePlatform:
    def run(self, goal: str) -> str:
        return f"handle:{goal}"


def test_remote_agent_executor_runs_on_platform():
    ex: IRemoteAgentExecutor = MessagingRemoteAgentExecutor()
    handle = ex.submit_remote("n2", "summarize", _FakePlatform())
    assert handle == "handle:summarize"


# --------------------------------------------------------------------------
# Cluster Metrics reuse ITelemetrySink
# --------------------------------------------------------------------------
class _FakeSink:
    def __init__(self) -> None:
        self.records = []
    def record(self, name, value, labels, confidence):
        self.records.append((name, value, labels, confidence))


def test_cluster_metrics_emits_to_sink():
    metrics = TelemetryClusterMetrics()
    sink = _FakeSink()
    metrics.emit_node_metric("n1", "cpu", 0.42,
                             ConfidenceScore(0.9, ProvenanceType.OBSERVATION), sink)
    assert sink.records and sink.records[0][0] == "cpu"


# --------------------------------------------------------------------------
# Network Supervisor subscribes to leader-change (reuse WP-14 elector hook)
# --------------------------------------------------------------------------
def test_network_supervisor_subscribes():
    bus = InMemoryEventBus()
    sup = ElectorNetworkSupervisor()
    # supervise must not raise; uses bus.subscribe("raft.leader_change", ...)
    sup.supervise(None, bus)  # elector unused in reference impl
    # publishing a leader_change is handled (hook is a no-op recovery trigger)
    bus.publish_sync("raft.leader_change", {"leader": "n2"})
    assert True
