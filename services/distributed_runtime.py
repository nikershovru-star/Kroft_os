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
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    Policy,
    Provenance,
    ProvenanceType,
    SemanticFact,
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
from contracts.i_memory import IMemoryStore
from contracts.i_network_transport import INetworkTransport, SoftLayerItem
from contracts.i_identity import ITrustRegistry
from contracts.i_cognitive_kernel import ILayeredMemory
from contracts.i_signature import (
    ISignatureProvider, attach_signature, check_signature, verify_envelope,
)
from contracts.cognitive_domain import CausalMark, NodeLamportClock
from contracts.i_signature import ReplayGuard
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
    (lamport, node_origin tiebreak). Wall-clock `updated_at` is NOT used for
    ordering (node clocks drift). On EVERY receive the LOCAL Lamport clock is
    advanced via `CausalMark.receive` — this is the ТЗ-CAUSAL-01 fix that makes
    merge causal instead of "whoever did more operations wins".
    """

    def __init__(self, self_node_id: str, clock: Optional["NodeLamportClock"] = None) -> None:
        self._node_id = self_node_id
        # ТЗ-RE-01 flag 1: SHARE the node's Lamport clock. If a node-level clock is
        # injected (e.g. the same instance the kernel + world use), federation
        # receive-events advance the SAME clock, keeping all causal marks consistent.
        self._clock = clock if clock is not None else NodeLamportClock(self_node_id)

    def publish_selective(self, world: WorldState, scope: str) -> List[dict]:
        out: List[dict] = []
        for key, val in world.facts.items():
            if scope in key or scope == "*":
                mark = world.facts_meta.get(key, CausalMark(world.node_id, 0))
                # ТЗ-WM-01 flag A sentinel: a CausalMark with the legacy default origin
                # ("kernel"/"local") means the clock was never wired to node_id. Do NOT
                # let it silently leak into federation — normalize to this node's id so
                # the origin is always a real node (and surface the defect via warning).
                origin = mark.node_origin
                if origin in ("kernel", "local"):
                    import warnings
                    warnings.warn(
                        f"publish_selective: fact '{key}' carried sentinel origin "
                        f"'{origin}' (clock not wired to node_id) — normalized to "
                        f"'{self._node_id}'")
                    origin = self._node_id
                out.append({"key": key, "value": val,
                            "node_origin": origin, "lamport": mark.lamport})
        return out

    def merge_remote(self, remote_facts: List[dict],
                     local_world: WorldState) -> WorldState:
        """Causal merge of REMOTE facts into LOCAL world state.

        A remote fact wins only if its CausalMark is GREATER than the local one (or
        local absent). Wall-clock `updated_at` is intentionally NOT used (gate C).
        Local facts survive unless overridden by a greater remote mark.

        ТЗ-CAUSAL-01: the node's OWN Lamport clock is advanced on receive
        (clock = max(local, received) + 1). Without this, Lamport degenerates into
        a per-node counter that picks "talkative" nodes — not causal order.
        """
        merged: Dict[str, str] = dict(local_world.facts)
        meta: Dict[str, CausalMark] = dict(local_world.facts_meta)
        # track the highest remote mark seen in THIS delivery
        max_remote = CausalMark(self._node_id, 0)
        for rf in remote_facts:
            key = rf["key"]
            remote_mark = CausalMark(rf["node_origin"], rf["lamport"])
            if remote_mark > max_remote:
                max_remote = remote_mark
            if key not in meta or remote_mark > meta[key]:
                merged[key] = rf["value"]
                meta[key] = remote_mark
        # advance local federation clock only if we observed a causally-NEWER remote
        # mark (ТЗ-CAUSAL-01 receive-rule). Duplicate delivery of the same message
        # does NOT keep inflating the clock — that is what makes replay idempotent.
        if max_remote.lamport > self._clock.mark.lamport:
            self._clock.receive(max_remote)
        return WorldState(node_id=self._node_id, facts=merged, facts_meta=meta,
                          confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION))

    def replicate_to(self, transport: "INetworkTransport", scope: str,
                     world: WorldState) -> None:
        """ТЗ-NW-01: real-network replication. Publish selective facts and ship them
        over the transport (wire lamport) so peers can run merge_remote on arrival.
        Implements the ISharedContext.replicate_to extension for real federation.
        """
        facts = self.publish_selective(world, scope)
        transport.send_facts(facts, self._node_id)


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


# -------------------------------------------------------------------------
# Network Federation (ТЗ-NW-01) — real-network federation of COGNITIVE data
# -------------------------------------------------------------------------
class NetworkFederationService:
    """Federates COGNITIVE data (CognitiveEvents + WorldState facts) between kernel
    nodes over a real transport (TcpEventBus via INetworkTransport adapter).

    Wires the receiver side so that causal merge (SharedContextService.merge_remote,
    Lamport receive-bump) runs on EVERY inbound fact — and the merged fact influences
    the receiver's Decision (FEDERATION COGNITIVE VALUE, not mere data replication).

    K6: depends on adapters ONLY through the INetworkTransport PORT (NetworkTransport
    is injected by the caller). Never imports a concrete adapter here.
    """

    def __init__(self, self_node_id: str,
                 shared: ISharedContext,
                 transport: INetworkTransport,
                 on_world_merged: "Optional[Callable[[WorldState], None]]" = None) -> None:
        self._node_id = self_node_id
        self._shared = shared
        self._transport = transport
        self._on_world_merged = on_world_merged
        self._local_world: Optional[WorldState] = None
        # receiver lock (ТЗ-NW-01 flag 1): once a kernel attaches, the receiver callback
        # is FINAL. A later external override of on_world_merged would silently drop the
        # kernel SSOT fold — so the setter is ignored after lock_receiver().
        self._receiver_locked = False
        # inbound handlers: route transport messages into causal merge
        transport.on_event(self._handle_remote_event)
        transport.on_facts(self._handle_remote_facts)
        # partition buffer: facts received while a peer was down are replayed on
        # reconnect (FIFO), then idempotent merge discards duplicates.
        self._replay_buffer: List[tuple] = []

    @property
    def receiver(self) -> "Optional[Callable[[WorldState], None]]":
        """The callback invoked on every causal merge (read-only, for verification)."""
        return self._on_world_merged

    @property
    def has_receiver(self) -> bool:
        return self._on_world_merged is not None

    def set_local_world(self, world: WorldState) -> None:
        self._local_world = world

    def on_world_merged(self, cb: "Callable[[WorldState], None]") -> None:
        """Public hook: set the receiver callback invoked on every causal merge.

        Ignored once the receiver is locked by attach_federation (ТЗ-NW-01 flag 1) —
        the kernel SSOT fold must not be silently replaced.
        """
        if self._receiver_locked:
            return
        self._on_world_merged = cb

    def lock_receiver(self) -> None:
        """Finalize the receiver callback. Called by CognitiveKernel.attach_federation
        right after binding, so subsequent overrides are no-ops (flag 1)."""
        self._receiver_locked = True

    def broadcast_event(self, event) -> None:
        """Ship a CognitiveEvent (carries its CausalMark) to all peers."""
        self._transport.send_event(event)

    def replicate_world(self, world: WorldState, scope: str = "*") -> None:
        """Publish local WorldState facts to peers over the transport (wire lamport)."""
        self._local_world = world
        self._shared.replicate_to(self._transport, scope, world)

    def _handle_remote_event(self, event) -> None:
        """A peer's CognitiveEvent arrived — re-emit through the shared context so the
        local kernel's decision logic can observe it (federation cognitive value)."""
        # The event carries a CausalMark; federation surfaces it to the receiver's
        # WorldState projection so the receiver's next Decision accounts for it.
        if self._local_world is not None:
            from contracts.cognitive_domain import CausalMark
            key = f"event:{event.type.value}:{event.ref_id}"
            mark = event.causal
            facts = dict(self._local_world.facts)
            meta = dict(self._local_world.facts_meta)
            facts[key] = event.ref_id
            if key not in meta or mark > meta[key]:
                meta[key] = mark
            self._local_world = WorldState(
                node_id=self._local_world.node_id,
                facts=facts, facts_meta=meta,
                confidence=self._local_world.confidence)
            if self._on_world_merged:
                self._on_world_merged(self._local_world)

    def _handle_remote_facts(self, facts: List[dict], sender_node_id: str) -> None:
        """Receiver side: causal merge of inbound WorldState facts (Lamport receive-bump
        lives in SharedContextService.merge_remote). Idempotent on replay."""
        if self._local_world is None:
            # buffer until local world is set (reconnect replay path)
            self._replay_buffer.append((facts, sender_node_id))
            return
        merged = self._shared.merge_remote(facts, self._local_world)
        self._local_world = merged
        if self._on_world_merged:
            self._on_world_merged(merged)

    def drain_replay_buffer(self) -> None:
        """Replay buffered facts after reconnect (idempotent merge)."""
        for facts, sender in self._replay_buffer:
            self._handle_remote_facts(facts, sender)
        self._replay_buffer.clear()


# --------------------------------------------------------------------------
# Federated Soft Memory Sync (ТЗ-FSE-01, ADR-066) — second federation channel
# --------------------------------------------------------------------------
def _causal_to_dict(cm) -> Optional[dict]:
    if cm is None:
        return None
    return {"node_origin": getattr(cm, "node_origin", ""), "lamport": getattr(cm, "lamport", 0)}


def _causal_from_dict(d) -> Optional["CausalMark"]:
    if not d:
        return None
    return CausalMark(d.get("node_origin", ""), int(d.get("lamport", 0)))


def _prov_to_dict(p) -> Optional[dict]:
    if p is None:
        return None
    return {"source": getattr(p, "source", ""), "actor": getattr(p, "actor", "")}


class FederationSoftMemorySync:
    """Federates the EVOLVED SOFT layer for collective self-evolution (ТЗ-FSE-01, ADR-066).

    LLM-free, K1 (services depend on contracts only). Reuses the NW-01
    ``INetworkTransport`` second channel (``cog.soft``) — does NOT invent a transport.

    Sender (``publish_soft_layer``): collects semantic facts + soft policies that pass
    the confidence-gate; HARD policies are NEVER shipped (O1). Each entry is a frozen
    ``SoftLayerItem`` wire-DTO carrying ``origin`` (provenance) so receivers know whose
    experience they adopt.

    Receiver (``_handle_remote_soft``): merges with a SECOND confidence-gate, dedup by
    content/body, preserves provenance (origin), and rejects anything that is not a
    known SOFT kind (HARD can never arrive — double protection).

    Read-side (SE-01: ``MemorySoftPolicySource`` / ``KnowledgeAwareReasoning``) is
    unchanged — it already reads ``ILayeredMemory``; federation only FILLS that layer.
    """
    def __init__(self, self_node_id: str, memory: "ILayeredMemory",
                 transport: "INetworkTransport", confidence_threshold: float = 0.5,
                 trust_registry: "Optional[ITrustRegistry]" = None,
                 trust_threshold: float = 0.0,
                 signature_provider: "Optional[ISignatureProvider]" = None,
                 replay_guard: "Optional[ReplayGuard]" = None) -> None:
        self._node_id = self_node_id
        self._memory = memory
        self._transport = transport
        self._threshold = confidence_threshold
        # ТЗ-IDT-01: optional trust-gating at the federation boundary. When None, the
        # receiver behaves EXACTLY like pre-IDT-01 (default permissive) — FSE-01 tests
        # stay green. When set, the receiver rejects batches from authors whose
        # trust_score_of(sender) < trust_threshold.
        self._trust_registry = trust_registry
        self._trust_threshold = trust_threshold
        # ТЗ-CRYPTO-01: when set, sign outgoing soft-layer items and verify incoming ones
        # before merge. None => legacy behaviour (no signing/verification).
        self._sig = signature_provider
        # ТЗ-CRYPTO-HARDEN-01: per-origin replay window (shared between client+server on this node).
        self._replay = replay_guard if replay_guard is not None else ReplayGuard()
        self._clock = NodeLamportClock(self_node_id)  # monotonic seq source for outgoing items
        self._receiver_bound = True  # subscribed once in __init__; never re-bound
        # NOTE: we do NOT disable the receiver here. The NW-01 "flag 1" lock prevents
        # EXTERNAL re-binding of the receiver callback to a different target; the local
        # receiver itself MUST stay live to merge inbound federated SOFT items. We simply
        # never re-subscribe, so the handler is fixed (idempotent attach is a no-op).
        transport.on_soft_layer(self._handle_remote_soft)

    @property
    def receiver(self):
        return self._handle_remote_soft

    def lock_receiver(self) -> None:
        """No-op (symmetry with ТЗ-NW-01 flag-1 attach pattern). The receiver is
        subscribed exactly once in __init__ and never re-bound, so external override is
        impossible by construction. Reception stays live (see _handle_remote_soft)."""
        self._receiver_bound = True

    def publish_soft_layer(self, memory: "ILayeredMemory", origin: Optional[str] = None) -> None:
        """Sender: ship learned SOFT layer (semantic + soft policies) with confidence-gate.
        HARD is NEVER shipped (O1)."""
        origin = origin or self._node_id
        items = []
        for f in memory.get_semantic():
            if f.confidence.value >= self._threshold:
                # ТЗ-CRYPTO-HARDEN-01: DISTINCT monotonic seq per item (replay-key via CausalMark.lamport).
                seq_mark = self._clock.tick()
                items.append(attach_signature(SoftLayerItem(
                    kind="semantic", content=f.content, confidence=f.confidence.value,
                    origin=origin, causal=_causal_to_dict(seq_mark),
                    provenance=_prov_to_dict(f.confidence.provenance),
                    author_id=origin,  # ТЗ-IDT-01: author == learning node
                ).to_wire(), self._sig))
        for p in memory.get_normative():
            if getattr(p, "layer", None) == "soft" and p.confidence.value >= self._threshold:
                seq_mark = self._clock.tick()  # distinct seq per item (see above)
                items.append(attach_signature(SoftLayerItem(
                    kind="soft_policy", content=p.body, confidence=p.confidence.value,
                    origin=origin, causal=_causal_to_dict(seq_mark),
                    provenance=_prov_to_dict(p.provenance),
                    author_id=origin,  # ТЗ-IDT-01: author == learning node
                ).to_wire(), self._sig))
            # HARD (layer != 'soft'): skipped — O1, never federated
        if items:
            self._transport.send_soft_layer(items, origin)

    def _handle_remote_soft(self, items: List[dict], sender: str) -> None:
        """Receiver: merge federated SOFT items with confidence-gate + dedup + provenance.

        ТЗ-IDT-01 trust-gating (OPTIONAL, default permissive): if a trust registry is wired,
        reject the ENTIRE batch when the sender's trust score is below the threshold. With
        no registry, behaviour is byte-for-byte the pre-IDT-01 FSE-01 receiver.
        """
        # ТЗ-IDT-01: optional trust-gate at the federation boundary.
        if self._trust_registry is not None:
            if self._trust_registry.trust_score_of(sender) < self._trust_threshold:
                return  # reject untrusted sender (low-trust items NEVER enter memory)
        for it in items:
            # ТЗ-CRYPTO-01 + HARDEN-01: verify origin/integrity/version/size AND replay BEFORE merge.
            # An unverified (tampered / wrong-key / unsigned / version-mismatch / oversized / replayed)
            # item is dropped — it never enters memory.
            if not verify_envelope(it, self._sig, replay_guard=self._replay):
                continue
            item = SoftLayerItem.from_wire(it)
            if item.confidence < self._threshold:
                continue  # receiver confidence-gate (double protection)
            if item.kind == "semantic":
                if any(f.content == item.content for f in self._memory.get_semantic()):
                    continue  # idempotent dedup
                self._memory.commit_semantic(SemanticFact(
                    id=f"fed-{item.origin}-{abs(hash(item.content)) % 10000}",
                    content=item.content,
                    confidence=ConfidenceScore(item.confidence, ProvenanceType.AGGREGATION),
                    causal=_causal_from_dict(item.causal) or CausalMark(item.origin, 0),
                    source_episodes=(),
                ))
            elif item.kind == "soft_policy":
                if any(p.body == item.content for p in self._memory.get_normative()):
                    continue  # idempotent dedup
                self._memory.commit_normative(Policy(
                    id=f"fed-soft-{item.origin}-{abs(hash(item.content)) % 10000}",
                    name=item.content,
                    layer="soft",
                    body=item.content,
                    confidence=ConfidenceScore(item.confidence, ProvenanceType.AGGREGATION),
                    provenance=Provenance(source=f"federated:{item.origin}", actor=item.origin),
                ))
            # unknown kind or HARD: ignored (O1 — HARD never federated)
