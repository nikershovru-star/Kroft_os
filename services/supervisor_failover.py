"""Supervisor failover — integrates Raft-lite with CRDT graph recovery (WP-14, ADR-043).

K8-compliant: services/. Imports contracts + stdlib. Leader node periodically
broadcasts CRDT ops (raft.sync); followers apply them (recovery/merge). On leader
change, followers keep working locally (graceful); new leader takes over sync.
Leader can trigger node recovery (reuse WP-10 SupervisorService.recover via cb).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from contracts.i_crdt_graph import ICrdtGraph
from contracts.i_leader_elector import ILeaderElector


class SupervisorFailover:
    """Bridges leader election with CRDT graph sync + node recovery."""

    def __init__(self, elector: ILeaderElector, graph: ICrdtGraph,
                 bus=None, recover_cb: Optional[Callable[[str], None]] = None,
                 sync_interval_sec: float = 0.2) -> None:
        self._elector = elector
        self._graph = graph
        self._bus = bus
        self._recover = recover_cb
        self._interval = sync_interval_sec
        self._timer: Optional[threading.Timer] = None
        self._running = False
        elector.on_leader_change(self._on_leader_change)

    def attach(self) -> None:
        if self._bus is not None:
            self._bus.subscribe("raft.sync", self._on_sync)
        self._elector.start(self._graph.node_id(), [])
        self._running = True
        if self._elector.is_leader():
            self._schedule_sync()

    def detach(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
        self._elector.stop()

    def _on_leader_change(self, leader: str) -> None:
        # new leader -> start sync; followers stop syncing (apply only)
        if self._timer:
            self._timer.cancel()
        if leader == self._graph.node_id() and self._elector.is_leader():
            self._schedule_sync()

    def _schedule_sync(self) -> None:
        if not self._running or not self._elector.is_leader() or self._bus is None:
            return
        self._timer = threading.Timer(self._interval, self._broadcast_sync)
        self._timer.daemon = True
        self._timer.start()

    def _broadcast_sync(self) -> None:
        if self._bus is not None and self._elector.is_leader():
            ops = self._graph.export_ops()
            if ops:
                self._bus.publish_sync("raft.sync", {"ops": [o.__dict__ for o in ops]})
        self._schedule_sync()

    def _on_sync(self, event: dict) -> None:
        # follower applies incoming CRDT ops (recovery/merge)
        if self._elector.is_leader():
            return
        ops = event.get("ops", [])
        from contracts.i_crdt_graph import CrdtOp
        crdt_ops = [CrdtOp(kind=o["kind"], node_id=o["node_id"], lamport=o["lamport"],
                          payload=o.get("payload", {}), origin=o.get("origin", ""))
                    for o in ops]
        if crdt_ops:
            self._graph.apply_ops(crdt_ops)

    def recover_node(self, node_id: str) -> None:
        """Leader-triggered recovery of a failed node (reuse WP-10)."""
        if self._recover:
            self._recover(node_id)
