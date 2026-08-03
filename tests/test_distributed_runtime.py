"""Tests for WP-14 Distributed Runtime (ADR-043, RFC-014).

Targets >=15 tests. Covers: CRDT concurrent writes / merge / idempotency,
Raft-lite leader election + failover, TCP EventBus fan-out, SupervisorFailover
recovery, network partition + reconnect. Negative proof-of-fire (K1/K8).
"""
import time

import pytest

from contracts.i_crdt_graph import ICrdtGraph
from contracts.i_leader_elector import ILeaderElector
from contracts.i_distributed_event_bus import IDistributedEventBus
from contracts.knowledge_graph import Edge, Node, NodeType, EdgeType
from adapters.crdt_graph import CrdtGraphEngine
from adapters.raft_lite import RaftLiteElector
from adapters.tcp_event_bus import TcpEventBus
from services.supervisor_failover import SupervisorFailover
from infrastructure.eventbus import InMemoryEventBus


# ---------- CRDT Graph ----------

def test_crdt_concurrent_same_node_lww():
    a = CrdtGraphEngine("a"); b = CrdtGraphEngine("b")
    a.add_node(Node(id="n1", type=NodeType.COMPONENT, label="A-version"))
    b.add_node(Node(id="n1", type=NodeType.COMPONENT, label="B-version"))
    a.merge(b)
    # higher lamport wins (b added after a in this sequence) -> B-version
    assert a.get_node("n1").label == "B-version"


def test_crdt_concurrent_diff_nodes_both_kept():
    a = CrdtGraphEngine("a"); b = CrdtGraphEngine("b")
    a.add_node(Node(id="n1", type=NodeType.COMPONENT, label="n1"))
    b.add_node(Node(id="n2", type=NodeType.COMPONENT, label="n2"))
    a.merge(b)
    assert a.get_node("n1") is not None and a.get_node("n2") is not None
    assert len(a.nodes()) == 2


def test_crdt_merge_idempotent():
    a = CrdtGraphEngine("a"); b = CrdtGraphEngine("b")
    a.add_node(Node(id="n1", type=NodeType.COMPONENT, label="n1"))
    b.add_node(Node(id="n2", type=NodeType.COMPONENT, label="n2"))
    a.merge(b); a.merge(b)  # double merge
    assert len(a.nodes()) == 2


def test_crdt_export_apply_ops():
    src = CrdtGraphEngine("src")
    src.add_node(Node(id="n1", type=NodeType.COMPONENT, label="x"))
    src.add_edge(Edge(source_id="n1", target_id="n0", type=EdgeType.REFERENCES))
    ops = src.export_ops()
    dst = CrdtGraphEngine("dst")
    dst.apply_ops(ops)
    assert dst.get_node("n1") is not None
    assert len(dst.edges()) == 1


def test_crdt_edges_lww():
    a = CrdtGraphEngine("a"); b = CrdtGraphEngine("b")
    a.add_edge(Edge(source_id="n1", target_id="n2", type=EdgeType.REFERENCES))
    b.add_edge(Edge(source_id="n1", target_id="n3", type=EdgeType.REFERENCES))
    a.merge(b)
    assert len(a.edges()) == 2  # different edges both kept


# ---------- Raft-lite ----------

def _cluster(n):
    bus = InMemoryEventBus()
    electors = []
    for i in range(n):
        e = RaftLiteElector(bus, heartbeat_sec=0.05, election_timeout_sec=0.15)
        e.start(f"node-{i}", [f"node-{j}" for j in range(n) if j != i])
        electors.append(e)
    return bus, electors


def test_raft_single_leader_elected():
    bus, els = _cluster(3)
    time.sleep(0.6)
    leaders = [e for e in els if e.is_leader()]
    assert len(leaders) == 1
    for e in els:
        assert e.current_leader() == leaders[0].current_leader()
    for e in els:
        e.stop()


def test_raft_leader_failover():
    bus, els = _cluster(3)
    time.sleep(0.5)
    leader = next(e for e in els if e.is_leader())
    leader.stop()  # leader down
    time.sleep(0.8)
    remaining = [e for e in els if e is not leader]
    new_leaders = [e for e in remaining if e.is_leader()]
    assert len(new_leaders) == 1
    for e in remaining:
        e.stop()


def test_raft_election_callback():
    bus = InMemoryEventBus()
    changes = []
    e = RaftLiteElector(bus, heartbeat_sec=0.05, election_timeout_sec=0.15)
    e.on_leader_change(lambda lid: changes.append(lid))
    e.start("n0", [])
    time.sleep(0.4)
    assert e.is_leader()
    assert any(c == "n0" for c in changes)
    e.stop()


# ---------- TCP EventBus ----------

def test_tcp_bus_fanout():
    b1 = TcpEventBus("a", 8791); b2 = TcpEventBus("b", 8792)
    received = []
    b2.subscribe("topic.x", lambda ev: received.append(ev))
    b2.join(["127.0.0.1:8791"])  # start b2 server first
    b1.join(["127.0.0.1:8792"])
    time.sleep(1.0)  # allow retry-connect to establish peers
    b1.publish_sync("topic.x", {"v": 1})
    time.sleep(0.6)
    assert len(received) >= 1, f"received={received}, b1.peers={b1.peers()}"
    b1.leave(); b2.leave()


def test_tcp_bus_peers():
    b1 = TcpEventBus("a", 8793); b2 = TcpEventBus("b", 8794)
    b2.join(["127.0.0.1:8793"])  # start b2 server first
    b1.join(["127.0.0.1:8794"])
    time.sleep(0.6)
    assert "127.0.0.1:8794" in b1.peers() or "127.0.0.1:8793" in b2.peers()
    b1.leave(); b2.leave()


# ---------- SupervisorFailover + partition/reconnect ----------

def test_failover_leader_broadcasts_to_follower():
    # ТЗ-NW-01 commit 1: determinize WP14-RACE. Replace wall-clock time.sleep polling
    # with explicit leader-election barriers (RaftLiteElector.wait_leader) so the test
    # wakes on the actual leadership event, not on timing luck.
    bus = InMemoryEventBus()
    leader_g = CrdtGraphEngine("leader")
    follower_g = CrdtGraphEngine("follower")
    el_leader = RaftLiteElector(bus, heartbeat_sec=0.05, election_timeout_sec=0.15)
    el_leader.start("leader", ["follower"])
    el_follower = RaftLiteElector(bus, heartbeat_sec=0.05, election_timeout_sec=0.15)
    el_follower.start("follower", ["leader"])
    fo = SupervisorFailover(el_follower, follower_g, bus=bus)
    fo.attach()
    # deterministic barrier: wait until leadership is decided (no sleep race)
    leader_id = el_leader.wait_leader(timeout=2.0)
    assert leader_id == "leader"
    assert el_leader.is_leader() and not el_follower.is_leader()
    # leader adds node, broadcasts via raft.sync
    leader_g.add_node(Node(id="shared", type=NodeType.COMPONENT, label="synced"))
    from contracts.i_crdt_graph import CrdtOp
    ops = leader_g.export_ops()
    bus.publish_sync("raft.sync", {"ops": [o.__dict__ for o in ops]})
    # deterministic barrier: wait until follower applies the synced node
    follower_g.wait_node("shared", timeout=2.0)
    assert follower_g.get_node("shared") is not None
    fo.detach()
    el_leader.stop(); el_follower.stop()


def test_raft_single_leader_elected():
    bus, els = _cluster(3)
    # determinic barrier instead of fixed sleep (WP14-RACE fix)
    leader = els[0].wait_leader(timeout=2.0)
    assert leader is not None
    leaders = [e for e in els if e.is_leader()]
    assert len(leaders) == 1
    for e in els:
        assert e.current_leader() == leaders[0].current_leader()
    for e in els:
        e.stop()


def test_raft_leader_failover():
    bus, els = _cluster(3)
    els[0].wait_leader(timeout=2.0)
    leader = next(e for e in els if e.is_leader())
    leader.stop()  # leader down
    # deterministic barrier: wait for a NEW leader to be elected among the rest
    new_leader = None
    for e in els:
        if e is not leader:
            new_leader = e.wait_leader(timeout=2.0)
            if new_leader:
                break
    assert new_leader is not None
    new_leaders = [e for e in els if e.is_leader()]
    assert len(new_leaders) == 1
    for e in els:
        e.stop()


def test_network_partition_reconnect_consistent():
    # two CRDT replicas; simulate partition (no merge), concurrent local writes,
    # then reconnect (merge) -> both converge
    a = CrdtGraphEngine("a"); b = CrdtGraphEngine("b")
    # partitioned: each writes locally
    a.add_node(Node(id="na", type=NodeType.COMPONENT, label="na"))
    b.add_node(Node(id="nb", type=NodeType.COMPONENT, label="nb"))
    # partition heals -> merge both ways
    a.merge(b); b.merge(a)
    assert a.get_node("nb") is not None
    assert b.get_node("na") is not None
    # symmetric convergence
    assert len(a.nodes()) == len(b.nodes()) == 2


# ---------- K1/K8 proof-of-fire ----------

def test_negative_k1_ports_clean():
    import inspect
    for mod in (ICrdtGraph, ILeaderElector, IDistributedEventBus):
        src = inspect.getsource(mod)
        assert "import services" not in src and "from services" not in src
        assert "import runtime" not in src and "from runtime" not in src
        assert "import adapters" not in src and "from adapters" not in src


def test_negative_k8_adapters_services_clean():
    import inspect
    src = (inspect.getsource(CrdtGraphEngine) + inspect.getsource(RaftLiteElector)
           + inspect.getsource(TcpEventBus) + inspect.getsource(SupervisorFailover))
    assert "import kernel" not in src and "from kernel" not in src
    assert "import runtime" not in src and "from runtime" not in src


def test_crdt_traverse_and_cycles():
    g = CrdtGraphEngine("g")
    g.add_node(Node(id="a", type=NodeType.COMPONENT, label="a"))
    g.add_node(Node(id="b", type=NodeType.COMPONENT, label="b"))
    g.add_edge(Edge(source_id="a", target_id="b", type=EdgeType.REFERENCES))
    assert len(g.traverse("a")) == 1
    assert len(g.find_cycles()) == 0
    g.add_edge(Edge(source_id="b", target_id="a", type=EdgeType.REFERENCES))
    assert len(g.find_cycles()) >= 1
