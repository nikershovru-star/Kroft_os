"""Raft-lite leader elector (WP-14, ADR-043).

K8-compliant: adapters/. Imports contracts + stdlib + threading. ONLY elects a
leader (term-based heartbeat + majority vote). NO log replication (per RFC-014).
Leader coordinates recovery (Supervisor failover); followers apply CRDT ops
locally. Heartbeats flow over an IDistributedEventBus (raft.heartbeat / raft.vote).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from contracts.i_leader_elector import ILeaderElector


class RaftLiteElector(ILeaderElector):
    """Minimal Raft: election only, no log replication.

    States: follower -> candidate -> leader. On start, node is follower. If no
    heartbeat from a leader within election_timeout, it becomes candidate, bumps
    term, votes for itself, and asks peers (via bus) for votes. Majority -> leader.
    Leader emits raft.heartbeat periodically so followers stay calm.
    """

    def __init__(self, bus, heartbeat_sec: float = 0.1, election_timeout_sec: float = 0.3) -> None:
        self._bus = bus
        self._heartbeat = heartbeat_sec
        self._timeout = election_timeout_sec
        self._node_id = ""
        self._peers: List[str] = []
        self._term = 0
        self._state = "follower"
        self._leader: Optional[str] = None
        self._votes: Dict[str, int] = {}
        self._last_heartbeat = 0.0
        self._lock = threading.RLock()
        self._timer: Optional[threading.Timer] = None
        self._hb_timer: Optional[threading.Timer] = None
        self._cb: Optional[Callable[[str], None]] = None
        self._running = False

    # --- ILeaderElector ---
    def start(self, node_id: str, peers: List[str]) -> None:
        with self._lock:
            self._node_id = node_id
            self._peers = list(peers)
            self._state = "follower"
            self._leader = None
            self._last_heartbeat = time.monotonic()
            self._running = True
        self._bus.subscribe("raft.heartbeat", self._on_heartbeat)
        self._bus.subscribe("raft.vote_request", self._on_vote_request)
        self._bus.subscribe("raft.vote_grant", self._on_vote_grant)
        self._schedule_election_check()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._timer:
            self._timer.cancel()
        if self._hb_timer:
            self._hb_timer.cancel()

    def is_leader(self) -> bool:
        with self._lock:
            return self._state == "leader"

    def current_leader(self) -> Optional[str]:
        with self._lock:
            return self._leader

    def term(self) -> int:
        with self._lock:
            return self._term

    def on_leader_change(self, cb: Callable[[str], None]) -> None:
        self._cb = cb

    def wait_leader(self, timeout: float = 2.0) -> Optional[str]:
        """Deterministic barrier: block until a leader is known (or timeout).

        Replaces wall-clock ``time.sleep`` polling in tests, which is the source of
        WP14-RACE. Wakes immediately on the ``on_leader_change`` event — no timing luck.
        """
        ev = threading.Event()

        def _cb(leader_id: str) -> None:
            ev.set()

        with self._lock:
            if self._leader is not None:
                return self._leader
            prev = self._cb
            self._cb = _cb
        try:
            ev.wait(timeout)
        finally:
            with self._lock:
                self._cb = prev
        with self._lock:
            return self._leader

    # --- internals ---
    def _schedule_election_check(self) -> None:
        with self._lock:
            if not self._running:
                return
        self._timer = threading.Timer(self._timeout, self._election_check)
        self._timer.daemon = True
        self._timer.start()

    def _election_check(self) -> None:
        with self._lock:
            if not self._running:
                return
            if self._state == "leader":
                self._schedule_election_check()
                return
            if time.monotonic() - self._last_heartbeat >= self._timeout:
                self._become_candidate()
        self._schedule_election_check()

    def _become_candidate(self) -> None:
        with self._lock:
            self._state = "candidate"
            self._term += 1
            self._votes = {self._node_id: 1}
        self._bus.publish_sync("raft.vote_request",
                               {"term": self._term, "from": self._node_id})
        # self-count majority? count peers+self
        with self._lock:
            cluster_size = len(self._peers) + 1
            if self._votes.get(self._node_id, 0) >= (cluster_size // 2 + 1):
                self._become_leader()

    def _on_vote_request(self, event: dict) -> None:
        if event.get("from") == self._node_id:
            return  # ignore our own broadcast
        with self._lock:
            term = event.get("term", 0)
            # only step down if the requester has a STRICTLY higher term;
            # equal-term concurrent requests must not reset a candidate.
            if term > self._term:
                self._term = term
                self._state = "follower"
                self._leader = None
            else:
                return
        self._bus.publish_sync("raft.vote_grant",
                               {"term": term, "from": self._node_id, "to": event.get("from")})

    def _on_vote_grant(self, event: dict) -> None:
        if event.get("from") == self._node_id:
            return  # ignore our own broadcast
        with self._lock:
            if event.get("to") != self._node_id or self._state != "candidate":
                return
            self._votes[event.get("from", event.get("to"))] = 1
            cluster_size = len(self._peers) + 1
            if sum(self._votes.values()) >= (cluster_size // 2 + 1):
                self._become_leader()

    def _become_leader(self) -> None:
        with self._lock:
            prev = self._leader
            self._state = "leader"
            self._leader = self._node_id
        self._bus.publish_sync("raft.heartbeat",
                               {"term": self._term, "from": self._node_id})
        self._schedule_heartbeat()
        if self._cb and prev != self._node_id:
            self._cb(self._node_id)

    def _schedule_heartbeat(self) -> None:
        with self._lock:
            if not self._running or self._state != "leader":
                return
        self._hb_timer = threading.Timer(self._heartbeat, self._send_heartbeat)
        self._hb_timer.daemon = True
        self._hb_timer.start()

    def _send_heartbeat(self) -> None:
        with self._lock:
            if self._state != "leader":
                return
        self._bus.publish_sync("raft.heartbeat",
                               {"term": self._term, "from": self._node_id})
        self._schedule_heartbeat()

    def _on_heartbeat(self, event: dict) -> None:
        with self._lock:
            term = event.get("term", 0)
            if term >= self._term:
                self._term = term
                self._leader = event.get("from")
                # acknowledge leader: a candidate steps down; a leader stays leader
                if self._state == "candidate":
                    self._state = "follower"
                self._last_heartbeat = time.monotonic()
