"""N2 — Local network CLI: parser + per-node config isolation (deterministic).

Covers the wiring that does NOT require booting a full KroftApp (heavy). The
end-to-end `network start` boot is covered by the background integration proof.
"""
import sys

import pytest

sys.path.insert(0, r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS")

from cli.parser import build_parser
from cli.commands import _make_node_config, _NETWORK, _net_status, _net_stop


def test_parser_network_start():
    a = build_parser().parse_args(["network", "start", "--nodes", "3", "--base-port", "9105"])
    assert a.command == "network"
    assert a.net_action == "start"
    assert a.nodes == 3
    assert a.base_port == 9105


def test_parser_network_status_and_nodes_alias():
    assert build_parser().parse_args(["network", "status"]).net_action == "status"
    assert build_parser().parse_args(["network", "nodes"]).net_action == "nodes"
    assert build_parser().parse_args(["network", "stop"]).net_action == "stop"


def test_make_node_config_isolation():
    c1 = _make_node_config("kroft-001", "127.0.0.1", 9101, "data/nodes", "SNAP.json")
    c2 = _make_node_config("kroft-002", "127.0.0.1", 9102, "data/nodes", "SNAP.json")
    # distinct identity / network / storage per node (ТЗ §4/§5/§6)
    assert c1.node_id == "kroft-001" and c2.node_id == "kroft-002"
    assert c1.network_port == 9101 and c2.network_port == 9102
    assert c1.state_root.endswith("kroft-001")
    assert c2.state_root.endswith("kroft-002")
    assert c1.network_host == c2.network_host == "127.0.0.1"


def test_status_reports_no_nodes_gracefully(capsys):
    _NETWORK.clear()
    _net_status()
    out = capsys.readouterr().out
    assert "no nodes running" in out


class _FakeApp:
    def __init__(self, node_id, host, port, state_root):
        self.config = type("C", (), {
            "node_id": node_id, "network_host": host,
            "network_port": port, "state_root": state_root,
        })()
        self.graph = None  # _net_status must tolerate missing graph


def test_status_renders_running_nodes(capsys):
    _NETWORK.clear()
    _NETWORK["kroft-001"] = _FakeApp("kroft-001", "127.0.0.1", 9101, "data/nodes/kroft-001")
    _NETWORK["kroft-002"] = _FakeApp("kroft-002", "127.0.0.1", 9102, "data/nodes/kroft-002")
    _net_status()
    out = capsys.readouterr().out
    assert "kroft-001" in out and "kroft-002" in out
    assert "9101" in out and "9102" in out
    assert "ONLINE" in out


def test_stop_on_empty_is_safe(capsys):
    _NETWORK.clear()
    _net_stop()  # must not raise
    assert "STOPPED" in capsys.readouterr().out
