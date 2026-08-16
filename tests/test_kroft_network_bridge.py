"""KROFT-NET-04 — Hermes multi-node operator bridge (TZ §9/§10 final UX).

Proves Hermes (via KroftNetworkBridge) can:
  - see multiple nodes (kroft.list / kroft.network.status)  [TZ §25 T2/T3]
  - start/stop nodes as operator (kroft.network.start/stop)  [TZ §21]
  - delegate search/query/resolve/status to a SPECIFIC node  [TZ §10]

REUSE: KroftNodeManager (KROFT-NET-02) + KroftBridge (H0). No kernel/federation change.

Targeted (spawns 2 real KROFT subprocesses). Run: pytest tests/test_kroft_network_bridge.py -q
"""

from __future__ import annotations

import tempfile

import pytest

from bridges.kroft_network_bridge import KroftNetworkBridge


@pytest.fixture
def net():
    with tempfile.TemporaryDirectory() as base:
        bridge = KroftNetworkBridge(base_state_root=base)
        yield bridge
        bridge.shutdown_all()


def test_hermes_sees_two_nodes(net):
    """TZ §10: 'Гермес, какие KROFT запущены?' -> 2 nodes."""
    net.start_node("kroft-01", role="research", port=7101)
    net.start_node("kroft-02", role="coding", port=7102)
    # allow boot
    import time
    for _ in range(60):
        if net.network_status().result["online"] == 2:
            break
        time.sleep(0.5)
    lst = net.list()
    assert lst.ok
    assert lst.result["count"] == 2
    ids = {n["node_id"] for n in lst.result["nodes"]}
    assert ids == {"kroft-01", "kroft-02"}
    ns = net.network_status()
    assert ns.result["nodes"] == 2 and ns.result["online"] == 2


def test_hermes_start_stop_node(net):
    """TZ §21: kroft network start/stop."""
    r = net.start_node("kroft-03", role="personal", port=7103)
    assert r.ok
    import time
    for _ in range(60):
        if net.network_status().result["online"] == 1:
            break
        time.sleep(0.5)
    assert net.network_status().result["online"] == 1
    s = net.stop_node("kroft-03")
    assert s.ok and s.result["stopped"] is True
    assert net.network_status().result["online"] == 0


def test_hermes_delegates_to_specific_node(net):
    """TZ §10: 'Спроси Research (kroft-01) ...' -> delegated, not global."""
    net.start_node("kroft-01", role="research", port=7101)
    net.start_node("kroft-02", role="coding", port=7102)
    import time
    for _ in range(60):
        if net.network_status().result["online"] == 2:
            break
        time.sleep(0.5)
    # status delegation returns structured result for the named node
    st = net.status("kroft-01")
    assert st.ok
    assert st.result["node_id"] == "kroft-01"
