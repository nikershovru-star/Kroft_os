"""KROFT-NET-01 — instance isolation (TZ §6/§30/§31).

Proves two KROFT instances booted with distinct ``state_root`` never share
graph/index/runtime state. Uses TEMP state roots (never the production
750MB snapshot). REUSE: boots the real KroftApp composition root with
``state_root`` set; the derivation in run_kroft.py isolates each node under
``<state_root>/<node_id>/``. No new federation / crypto / kernel code.

Targeted (not the full 1640-test suite). Run:
    pytest tests/test_kroft_net_isolation.py -q
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace

import pytest

from composition.run_kroft import KroftApp, KroftConfig


def _boot(node_id: str, state_root: str) -> KroftApp:
    cfg = KroftConfig(
        node_id=node_id,
        state_root=state_root,
        knowledge_snapshot=None,  # forced: state_root derivation wins
        llm="none",
        embedding="none",
        federation=False,
        run_demo=False,
        agent_runtime=False,
        router=False,
    )
    return KroftApp(cfg)


def test_state_root_derives_isolated_snapshot_path():
    with tempfile.TemporaryDirectory() as root:
        app = _boot("kroft-01", root)
        expected = os.path.join(root, "kroft-01", "_snapshot.json")
        assert app._snapshot_store is not None
        assert app._snapshot_store._path == expected
        # runtime store lives in the same node dir -> also isolated
        rt = os.path.join(root, "kroft-01", "_runtime_snapshot.json")
        assert app._runtime_store._path == rt


def test_two_instances_isolated_state_roots():
    """TZ §30/§31: KROFT-01 mutation must NOT change KROFT-02."""
    with tempfile.TemporaryDirectory() as root:
        a = _boot("kroft-01", root)
        b = _boot("kroft-02", root)
        # distinct snapshot files
        assert a._snapshot_store._path != b._snapshot_store._path
        assert os.path.dirname(a._snapshot_store._path) != os.path.dirname(
            b._snapshot_store._path
        )
        # distinct in-memory registries (per-instance, not singleton)
        assert a.identity is not b.identity
        assert a.trust is not b.trust
        # distinct node identity
        assert a.config.node_id == "kroft-01"
        assert b.config.node_id == "kroft-02"
        # no shared mutable graph object
        assert a.graph is not b.graph


def test_legacy_no_state_root_unchanged():
    """When state_root is None, legacy knowledge_snapshot default is preserved."""
    cfg = KroftConfig(node_id="nodeX", state_root=None)
    # default knowledge_snapshot points at the KROFT_KNOWLEDGE_FOUNDATION snapshot
    assert cfg.knowledge_snapshot is not None
    assert "KROFT_KNOWLEDGE_FOUNDATION" in cfg.knowledge_snapshot
