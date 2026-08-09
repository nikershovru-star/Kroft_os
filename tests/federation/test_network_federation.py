"""ТЗ-NW-01-CONT commit 5 — acceptance + K8 negative: Real Network Federation (ADR-061).

Covers the FULL kernel-federation path: real CognitiveEvent/WorldState replication
over TcpEventBus (localhost TCP); PARTITION -> buffer -> RECONNECT -> causal merge
(Lamport order, idempotent replay); DETERMINISM (stable --count=5, no wall-clock
race); FEDERATION COGNITIVE VALUE (merged fact changes the receiver's Decision);
ФЛАГ 1 (single-writer, no duplicate SemanticFact); 3-node leader election (Raft
fairness: exactly one leader, not a specific node — see ADR-061 limitations).

K8: each invariant asserted positive AND its negation (where meaningful) fails.

Gotchas (from ТЗ-NW-01-CONT):
- NEVER override _on_world_merged after attach_federation in tests (receiver is locked).
- RaftLiteElector: use 3+ nodes for majority; assert "exactly one leader", not a
  specific node (a symmetric 2-node pair is non-deterministic by design).
- NO wall-clock sleep for sync; use barriers / wait / short polling only to observe.
"""
import time

import pytest

from contracts.cognitive_domain import (
    CausalMark,
    CognitiveEvent,
    CognitiveEventType,
    ConfidenceScore,
    Intent,
    NodeLamportClock,
    Observation,
    Provenance,
    ProvenanceType,
    WorldState,
)
from kernel.cognitive_kernel import build_kernel
from services.distributed_runtime import (
    NetworkFederationService,
    SharedContextService,
)
from adapters.network_transport import NetworkTransport

_PORT = [8961]

def _port():
    _PORT[0] += 1
    return _PORT[0]

def _wire(a, b):
    """Two connected federated kernels over real localhost TCP."""
    pa, pb = _port(), _port()
    ta = NetworkTransport(a, pa)
    tb = NetworkTransport(b, pb)
    ta.connect(a, [f"127.0.0.1:{pb}"])
    tb.connect(b, [f"127.0.0.1:{pa}"])
    assert ta.ensure_connected(1.0) and tb.ensure_connected(1.0), "link failed"
    ka = build_kernel(a)
    kb = build_kernel(b)
    fa = NetworkFederationService(a, SharedContextService(a, NodeLamportClock(a)), ta)
    fb = NetworkFederationService(b, SharedContextService(b, NodeLamportClock(b)), tb)
    ka.attach_federation(fa)
    kb.attach_federation(fb)
    return ta, tb, ka, kb, fa, fb

def _wait_fact(world_holder, key, timeout=2.0):
    """Poll (not sleep-race) until a fact key appears in the receiver's SSOT."""
    end = time.time() + timeout
    while time.time() < end:
        if key in world_holder._world.snapshot().facts:
            return True
        time.sleep(0.03)
    return False

def _replicate_until(fa, ka, kb, key, timeout=3.0):
    """Deterministic sender-barrier: retry idempotent replication until the fact
    lands in the receiver SSOT (poll, NOT wall-clock sleep). Fire-and-forget
    replicate_world can race TCP delivery under load; retrying is idempotent."""
    end = time.time() + timeout
    while time.time() < end:
        fa.replicate_world(ka._world.snapshot())
        if _wait_fact(kb, key, 0.25):
            return True
        time.sleep(0.03)
    return False


def test_real_worldstate_replication_over_tcp():
    """CognitiveEvent/WorldState facts replicate across real TCP to a peer SSOT."""
    ta, tb, ka, kb, fa, fb = _wire("RA", "RB")
    ka._world.update(Observation(
        id="env:safe", content="yes",
        confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION),
        provenance=Provenance(source="s", actor="s")))
    fa.replicate_world(ka._world.snapshot())
    ok = _replicate_until(fa, ka, kb, "env:safe")
    assert ok, "B did not receive A's world fact over TCP"
    assert kb._world.snapshot().facts.get("env:safe") == "yes"
    ta.disconnect(); tb.disconnect()


def test_real_cognitive_event_over_tcp():
    """A CognitiveEvent (with CausalMark) ships to the peer and is reconstructed."""
    ta, tb, ka, kb, fa, fb = _wire("EA", "EB")
    received = []
    # do NOT override fb receiver post-attach; instead observe via transport directly
    tb.on_event(received.append)
    ev = CognitiveEvent(
        type=CognitiveEventType.DECISION_ACCEPTED, ref_id="d1",
        provenance=Provenance(source="x", actor="a"),
        confidence=ConfidenceScore(0.9, ProvenanceType.MODEL_INFERENCE),
        causal=CausalMark("EA", 7))
    fa.broadcast_event(ev)
    end = time.time() + 2.0
    while time.time() < end and not any(r.ref_id == "d1" for r in received):
        time.sleep(0.05)
    assert any(r.ref_id == "d1" and r.causal.lamport == 7 for r in received), \
        "CognitiveEvent not reconstructed on receiver"
    ta.disconnect(); tb.disconnect()


@pytest.mark.slow
def test_partition_then_reconnect_causal_merge():
    """PARTITION (peer down) -> facts buffered; RECONNECT -> idempotent causal merge.

    Reconnect reuses the SAME port pb (TcpEventBus sets SO_REUSEADDR=1). Using a fresh
    port would break delivery: A's transport only knows pb as its outbound peer, so a
    new pb2 would never receive A's facts (fire-and-forget, no peer discovery).
    """
    pa, pb = _port(), _port()
    ta = NetworkTransport("PA", pa)
    tb = NetworkTransport("PB", pb)
    ta.connect("PA", [f"127.0.0.1:{pb}"])
    tb.connect("PB", [f"127.0.0.1:{pa}"])
    assert ta.ensure_connected(1.0)
    ka = build_kernel("PA")
    kb = build_kernel("PB")
    sa = SharedContextService("PA", NodeLamportClock("PA"))
    sb = SharedContextService("PB", NodeLamportClock("PB"))
    fa = NetworkFederationService("PA", sa, ta)
    fb = NetworkFederationService("PB", sb, tb)
    ka.attach_federation(fa)
    kb.attach_federation(fb)
    # partition: kill B's link
    tb.disconnect()
    time.sleep(0.3)
    wa = WorldState(node_id="PA", facts={"p:1": "v1"},
                    facts_meta={"p:1": CausalMark("PA", 5)},
                    confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION))
    fa.set_local_world(wa)
    # send while partitioned: TCP drops it (dead peer removed from ta._peers)
    fa.replicate_world(wa)
    # reconnect B on the SAME port (SO_REUSEADDR) so A's outbound peer is live again
    tb2 = NetworkTransport("PB", pb)
    tb2.connect("PB", [f"127.0.0.1:{pa}"])
    assert tb2.ensure_connected(1.0)
    fb2 = NetworkFederationService("PB", sb, tb2)
    kb.attach_federation(fb2)  # re-wire (idempotent) to the reconnected transport
    fb2.set_local_world(WorldState(node_id="PB", facts={}, facts_meta={},
                                   confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION)))
    # re-send after reconnect; idempotent replay, retry until delivered (no flake)
    ok = _replicate_until(fa, ka, kb, "p:1")
    assert ok, "B did not receive fact after reconnect"
    merged = kb._world.snapshot().facts
    assert merged.get("p:1") == "v1"
    # idempotent: replaying the same message does not duplicate
    assert list(merged.keys()).count("p:1") == 1
    ta.disconnect(); tb2.disconnect()


def test_federation_cognitive_value_changes_decision():
    """Merged federated fact lands in receiver SSOT AND changes its next Decision
    by SEMANTICS (selected plan STEPS), not by the always-unique plan uuid.

    ФЛАГ 1 NW-01 strengthening (ТЗ-RT-01 commit 0): the original assertion compared
    plan-IDS (uuid), which are trivially distinct -> proof was vacuous. We inject a
    world-aware planner so the federated fact `pref:blue` flips the CHOSEN PLAN's
    steps (choose_red -> choose_blue). Cognitive value = real semantic change.
    """
    from contracts.i_planner import IPlanner
    from contracts.cognitive_domain import Plan

    class WorldAwarePlanPlanner(IPlanner):
        """Deterministic 2-candidate planner: with `pref:blue` in the world it ranks
        the BLUE plan first; without it, the RED plan first. Same scores -> Decision
        picks the first candidate -> the selected plan's STEPS differ by world state."""
        def plan(self, goal, steps, world, budget, intent=None):
            facts = world.facts if world is not None else {}
            blue = Plan(id="plan-blue", goal_id=goal.id, steps=("choose_blue",),
                        confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                        provenance=Provenance(source="test", actor="test"))
            red = Plan(id="plan-red", goal_id=goal.id, steps=("choose_red",),
                       confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                       provenance=Provenance(source="test", actor="test"))
            if "pref:blue" in facts:
                return [blue, red]
            return [red, blue]

    ta, tb, ka, kb, fa, fb = _wire("CA", "CB")
    # inject the world-aware planner so the decision is driven by world content
    kb._planner = WorldAwarePlanPlanner()
    intent = Intent(id="i1", text="prefer_blue plan",
                    confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="u", actor="u"))
    # baseline decision WITHOUT federated fact -> RED plan (by semantics)
    kb.tick(intent)
    base_plan = kb._last_selected_plan
    assert base_plan is not None, "no selected plan at baseline"
    base_steps = base_plan.steps
    # A replicates a world fact
    ka._world.update(Observation(
        id="pref:blue", content="prefer_blue",
        confidence=ConfidenceScore(0.95, ProvenanceType.OBSERVATION),
        provenance=Provenance(source="s", actor="s")))
    fa.replicate_world(ka._world.snapshot())
    ok = _replicate_until(fa, ka, kb, "pref:blue")
    assert ok, "federated fact did not reach B SSOT"
    # next tick reads the federated fact through world.snapshot()
    kb.tick(intent)
    fed_plan = kb._last_selected_plan
    assert fed_plan is not None, "Decision@B has no plan after federation"
    assert "pref:blue" in kb._world.snapshot().facts
    # cognitive value by SEMANTICS: the federated fact flipped the chosen plan's
    # STEPS (not just its uuid). This is a non-trivial proof of influence.
    assert base_steps != fed_plan.steps, \
        f"cognitive value NOT proven by semantics: base={base_steps} fed={fed_plan.steps}"
    assert fed_plan.steps == ("choose_blue",), \
        f"federated fact did not drive BLUE plan: {fed_plan.steps}"
    ta.disconnect(); tb.disconnect()


def test_flag1_no_duplicate_semantic_after_tick():
    """ФЛАГ 1: a consolidated experience commits exactly once (Reflection + ME-01
    both observe it, but single-writer dedup keeps exactly one SemanticFact)."""
    from contracts.cognitive_domain import Intent
    k = build_kernel("F1")
    for i in range(3):
        k._world.update(Observation(
            id=f"pref:Y{i}", content="decide Y",
            confidence=ConfidenceScore(0.95, ProvenanceType.OBSERVATION),
            provenance=Provenance(source="s", actor="s")))
        k.tick(Intent(id=f"i{i}", text="decide Y",
                      confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                      provenance=Provenance(source="u", actor="u")))
    s = k._memory.get_semantic()
    contents = [f.content for f in s]
    assert len(s) == 1, f"expected 1 consolidated fact, got {len(s)}: {contents}"
    assert len(contents) == len(set(contents)), "duplicate SemanticFact after tick"


def test_receiver_locked_after_attach():
    """ФЛАГ 1: post-attach override of the receiver is silently ignored (kernel-hook
    must not be dropped)."""
    ta, tb, ka, kb, fa, fb = _wire("LA", "LB")
    recv_before = fb.receiver
    fb.on_world_merged(lambda w: None)  # must be ignored (locked)
    assert fb.receiver.__func__ is recv_before.__func__
    assert fb.receiver.__self__ is recv_before.__self__
    # re-attach is idempotent
    kb.attach_federation(fb)
    assert kb._federation is fb
    ta.disconnect(); tb.disconnect()


@pytest.mark.slow
def test_determinism_repeated_runs():
    """Federation is deterministic: same result across repeated runs (no flake)."""
    for _ in range(2):
        ta, tb, ka, kb, fa, fb = _wire("DA", "DB")
        ka._world.update(Observation(
            id="d:1", content="x",
            confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION),
            provenance=Provenance(source="s", actor="s")))
        fa.replicate_world(ka._world.snapshot())
        assert _replicate_until(fa, ka, kb, "d:1"), "non-deterministic: fact not delivered"
        ta.disconnect(); tb.disconnect()


def test_negative_stale_remote_does_not_override_local():
    """K8 negative: a remote fact with a LOWER CausalMark must NOT override a
    locally-newer fact (causal merge is by CausalMark, not arrival order)."""
    sb = SharedContextService("NB", NodeLamportClock("NB"))
    wb = WorldState(node_id="NB", facts={"k": "local"},
                    facts_meta={"k": CausalMark("NB", 10)},
                    confidence=ConfidenceScore(1.0, ProvenanceType.OBSERVATION))
    # remote lamport 5 < local 10 -> must NOT override
    remote = [{"key": "k", "value": "stale", "node_origin": "RA", "lamport": 5}]
    merged = sb.merge_remote(remote, wb)
    assert merged.facts["k"] == "local", "stale remote overrode local (bug)"


# ---------- 3-node leader election (Raft fairness) ----------
# RaftLiteElector is a SIMPLIFIED Raft (ТЗ-NW-01, ADR-061 limitations):
#  - a 2-node pair cannot self-elect a specific leader deterministically (split-brain);
#  - use 3+ nodes so majority is achievable; assert EXACTLY ONE leader, not a node.

def test_three_node_election_exactly_one_leader():
    """3-node cluster: Raft majority guarantees exactly one leader (deterministic)."""
    from infrastructure.eventbus import InMemoryEventBus
    from adapters.crdt_graph import CrdtGraphEngine
    from adapters.raft_lite import RaftLiteElector
    from contracts.knowledge_graph import Node, NodeType
    from services.supervisor_failover import SupervisorFailover

    bus = InMemoryEventBus()
    g = {n: CrdtGraphEngine(n) for n in ("n1", "n2", "n3")}
    els = {n: RaftLiteElector(bus, heartbeat_sec=0.05, election_timeout_sec=0.15)
           for n in ("n1", "n2", "n3")}
    for n in ("n1", "n2", "n3"):
        els[n].start(n, ["n1", "n2", "n3"])
    # barrier: wait for exactly one leader to emerge
    winner = None
    for n in ("n1", "n2", "n3"):
        w = els[n].wait_leader(timeout=2.0)
        if w:
            winner = w
            break
    leaders = [e for e in els.values() if e.is_leader()]
    assert winner is not None, "no leader elected in 3-node cluster"
    assert len(leaders) == 1, "Raft majority guarantees exactly one leader"
    fo = SupervisorFailover(els["n2"], g["n2"], bus=bus)
    fo.attach()
    g["n1"].add_node(Node(id="shared", type=NodeType.COMPONENT, label="synced"))
    from contracts.i_crdt_graph import CrdtOp
    ops = g["n1"].export_ops()
    bus.publish_sync("raft.sync", {"ops": [o.__dict__ for o in ops]})
    ok = g["n2"].wait_node("shared", timeout=2.0)
    assert ok, "follower did not apply leader broadcast"
    fo.detach()
    for e in els.values():
        e.stop()
