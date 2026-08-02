"""Local TCP EventBus — drop-in IEventBus over localhost TCP (WP-14, ADR-043).

K8-compliant: adapters/. Pure stdlib (socket + threading + json). Minimal pub/sub:
each node runs a TCP listener; publish() delivers locally + fans out to connected
peers. Partition -> sockets drop, local publish continues; reconnect re-establishes
peer links. (gRPC transport can be added later as another adapter.)
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Callable, Dict, List

from contracts.i_distributed_event_bus import IDistributedEventBus


class TcpEventBus(IDistributedEventBus):
    def __init__(self, node_id: str, port: int, host: str = "127.0.0.1") -> None:
        self._node_id = node_id
        self._host = host
        self._port = port
        self._subs: Dict[str, List[Callable]] = {}
        self._subs_lock = threading.RLock()
        self._peers: Dict[str, socket.socket] = {}
        self._peers_lock = threading.RLock()
        self._server: Optional[socket.socket] = None
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None

    # --- IEventBus ---
    def subscribe(self, topic: str, handler: Callable) -> None:
        with self._subs_lock:
            self._subs.setdefault(topic, []).append(handler)

    def publish(self, topic: str, event: dict) -> None:
        self.publish_sync(topic, event)

    def publish_sync(self, topic: str, event: dict) -> None:
        # local delivery
        self._deliver(topic, event)
        # fan-out to peers
        msg = json.dumps({"topic": topic, "event": event, "from": self._node_id}).encode("utf-8")
        with self._peers_lock:
            dead = []
            for pid, sock in self._peers.items():
                try:
                    sock.sendall(len(msg).to_bytes(4, "big") + msg)
                except OSError:
                    dead.append(pid)
            for pid in dead:
                self._peers.pop(pid, None)

    # --- distributed ---
    def join(self, seed_nodes: List[str]) -> None:
        self._running = True
        self._start_server()
        for seed in seed_nodes:
            self._connect_peer(seed)

    def leave(self) -> None:
        self._running = False
        with self._peers_lock:
            for sock in self._peers.values():
                try:
                    sock.close()
                except OSError:
                    pass
            self._peers.clear()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass

    def peers(self) -> List[str]:
        with self._peers_lock:
            return list(self._peers.keys())

    # --- internals ---
    def _start_server(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._host, self._port))
        srv.listen(8)
        srv.settimeout(0.5)
        self._server = srv
        self._listener_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._listener_thread.start()

    def _accept_loop(self) -> None:
        while self._running and self._server:
            try:
                conn, _ = self._server.accept()
            except OSError:
                break
            except Exception:
                continue
            self._spawn_reader(conn)

    def _connect_peer(self, seed: str) -> None:
        try:
            host, port = seed.split(":")
            sock = socket.create_connection((host, int(port)), timeout=2.0)
            with self._peers_lock:
                self._peers[seed] = sock
            self._spawn_reader(sock)
        except OSError:
            pass  # partition: peer unreachable now; reconnect on next join/heartbeat

    def _spawn_reader(self, sock: socket.socket) -> None:
        t = threading.Thread(target=self._read_loop, args=(sock,), daemon=True)
        t.start()

    def _read_loop(self, sock: socket.socket) -> None:
        while self._running:
            try:
                hdr = sock.recv(4)
                if not hdr:
                    break
                size = int.from_bytes(hdr, "big")
                buf = b""
                while len(buf) < size:
                    chunk = sock.recv(size - len(buf))
                    if not chunk:
                        break
                    buf += chunk
                if not buf:
                    break
                msg = json.loads(buf.decode("utf-8"))
                self._deliver(msg["topic"], msg["event"])
            except (OSError, ValueError, KeyError):
                break
        # peer dropped (partition) -> remove
        with self._peers_lock:
            for pid, s in list(self._peers.items()):
                if s is sock:
                    self._peers.pop(pid, None)

    def _deliver(self, topic: str, event: dict) -> None:
        with self._subs_lock:
            handlers = list(self._subs.get(topic, []))
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass
