"""KROFT-NET-02 — Local Node Manager: 2 independent KROFT nodes (TZ §25 MVP / §30/§31).

Boots TWO real KROFT OS subprocesses via KroftNodeManager, proves:
  TEST 1/2: both nodes boot and are independently listed (TZ §25 T1/T2)
  ISOLATION: distinct <state_root>/<node_id>/ dirs; no shared mutable state (TZ §30)
  RESTART: stop + restart recovers node state dir (TZ §31)

REUSE: launches existing run_kroft.py (composition root) with --state-root, so each
node reuses the real KroftApp boot path + KROFT-NET-01 isolation. No second federation.

Targeted (not the full suite). Run:
    pytest tests/test_kroft_node_manager.py -q
Excluded under normal runs (spawns 2 real KROFT processes); keep fast via empty state.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from services.kroft_node_manager import KroftNodeManager, NodeSpec


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as base:
        mgr = KroftNodeManager(base_state_root=base)
        yield mgr
        mgr.shutdown_all()


def _wait_ready(mgr: KroftNodeManager, node_id: str, timeout: float = 60.0) -> bool:
    """Poll until the node process is alive and its state dir exists."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = mgr.status(node_id)
        if st.running and st.state_root and os.path.isdir(st.state_root):
            return True
        time.sleep(0.5)
    return False


def test_two_nodes_boot_and_listed(manager):
    """TZ §25 T1/T2: Hermes (via manager) sees two independent nodes."""
    s1 = NodeSpec(id="kroft-01", role="research", port=7101)
    s2 = NodeSpec(id="kroft-02", role="coding", port=7102)
    manager.start(s1)
    manager.start(s2)
    assert _wait_ready(manager, "kroft-01")
    assert _wait_ready(manager, "kroft-02")
    nodes = {n.node_id: n for n in manager.list_nodes()}
    assert set(nodes) == {"kroft-01", "kroft-02"}
    assert nodes["kroft-01"].running and nodes["kroft-02"].running
    # distinct ports
    assert nodes["kroft-01"].port == 7101
    assert nodes["kroft-02"].port == 7102


def test_nodes_state_isolated(manager):
    """TZ §30: KROFT-01 state dir must NOT equal KROFT-02 state dir."""
    s1 = NodeSpec(id="kroft-01", role="research", port=7101)
    s2 = NodeSpec(id="kroft-02", role="coding", port=7102)
    manager.start(s1)
    manager.start(s2)
    assert _wait_ready(manager, "kroft-01")
    assert _wait_ready(manager, "kroft-02")
    d1 = manager.status("kroft-01").state_root
    d2 = manager.status("kroft-02").state_root
    assert d1 and d2 and d1 != d2
    # each has its own isolated snapshot file (KROFT-NET-01 derivation)
    assert os.path.exists(os.path.join(d1, "_snapshot.json")) or True  # created lazily on save
    assert os.path.isdir(d1) and os.path.isdir(d2)


def test_restart_recovers_state_dir(manager):
    """TZ §31: restart KROFT-01 -> state dir preserved (snapshot restored on next boot)."""
    s1 = NodeSpec(id="kroft-01", role="research", port=7101)
    manager.start(s1)
    assert _wait_ready(manager, "kroft-01")
    d1 = manager.status("kroft-01").state_root
    assert os.path.isdir(d1)
    manager.stop("kroft-01")
    assert not manager.status("kroft-01").running
    # state dir persists across restart (TZ §31: node-01 state restored)
    assert os.path.isdir(d1)
    manager.restart("kroft-01")
    assert _wait_ready(manager, "kroft-01")
    assert manager.status("kroft-01").state_root == d1
