"""N1 — Two-node runtime: isolation primitives (deterministic, no heavy boot).

Proves:
- ReferenceIdentityRegistry save/load round-trip (per-node persistence, К5).
- TcpEventBus binds distinct (host, port) per node -> both listeners up
  (the REAL N1 network-isolation mechanism: distinct config, not OS collision).

NOTE (Windows caveat, documented not asserted): on Windows `SO_REUSEADDR` permits
two listeners on the SAME port, so the OSError handler in TcpEventBus._start_server
does NOT act as a collision detector on Windows. Port isolation is a CONFIG
responsibility (distinct port per node, ТЗ §6) — verified below.
"""
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS")

from kernel.identity import ReferenceIdentityRegistry
from contracts.i_identity import AgentIdentity
from adapters.tcp_event_bus import TcpEventBus


def test_identity_save_load_roundtrip():
    reg = ReferenceIdentityRegistry()
    reg.register(AgentIdentity(agent_id="kroft-001", specialization="alpha", trust_level=0.9))
    reg.register(AgentIdentity(agent_id="kroft-002", specialization="beta", trust_level=0.5))
    path = os.path.join(tempfile.mkdtemp(), "node", "identity.json")
    reg.save(path)
    assert os.path.isfile(path), "save() must write the identity file"
    loaded = ReferenceIdentityRegistry.load(path)
    assert loaded.get("kroft-001").agent_id == "kroft-001"
    assert loaded.get("kroft-001").trust_level == 0.9
    assert loaded.get("kroft-002").agent_id == "kroft-002"


def test_identity_load_missing_file_is_empty():
    reg = ReferenceIdentityRegistry.load(os.path.join(tempfile.mkdtemp(), "nope", "missing.json"))
    assert reg.get("kroft-001") is None
    assert reg.has("kroft-001") is False


def test_two_buses_distinct_ports_both_up():
    """ТЗ §6 / §11: two nodes bind distinct ports -> both listeners online."""
    bus_a = TcpEventBus(node_id="kroft-001", port=19311, host="127.0.0.1")
    bus_b = TcpEventBus(node_id="kroft-002", port=19312, host="127.0.0.1")
    bus_a.join([])
    bus_b.join([])
    time.sleep(0.2)
    try:
        assert bus_a._server is not None, "A listener must be up"
        assert bus_b._server is not None, "B listener must be up"
        assert bus_a._port != bus_b._port, "ports must differ for isolation"
    finally:
        bus_a.leave()
        bus_b.leave()


def test_bus_bind_error_surfaces_clear_oserror():
    """When bind genuinely fails (busy port on platforms that enforce it, or
    permission denied), the handler raises a clear OSError rather than a raw
    traceback. Skipped on Windows where SO_REUSEADDR allows dual-bind."""
    import socket

    if os.name == "nt":
        pytest.skip("Windows SO_REUSEADDR permits same-port dual-bind; collision "
                    "is a config responsibility, not OS-detected.")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 19313))
    srv.listen(1)
    try:
        bus = TcpEventBus(node_id="x", port=19313, host="127.0.0.1")
        with pytest.raises(OSError):
            bus.join([])
    finally:
        srv.close()
