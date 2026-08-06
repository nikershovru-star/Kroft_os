"""ТЗ-DESKTOP-01 (ADR-097) — read-only observability dashboard K8 tests (Флаг 1b, separate).

Final capability stage (Stage 8): a read-only, deterministic snapshot of kernel state (memory,
agents, trust, models, tasks, FSM state) + text/JSON renderer. K5: reuses OBS-01 surfaces only as
data (does NOT duplicate ILiveMetricsCollector); the snapshotter is a PURE aggregator/renderer that
takes read-only providers, so it structurally cannot mutate the kernel (O1-style safe observation).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from composition.desktop_dashboard_factory import build_default_dashboard
from contracts.i_dashboard import DashboardSnapshot, IDashboard
from contracts.i_identity import AgentIdentity, TrustMeta
from kernel.identity import ReferenceIdentityRegistry, ReferenceTrustRegistry
from services.desktop_dashboard import DashboardSnapshotter
from services.memory_platform import InMemoryProceduralMemory


def _fake_kernel(state_name="DELIBERATE", node_id="nodeA"):
    return SimpleNamespace(_state=SimpleNamespace(name=state_name), _node_id=node_id)


def _fake_task_store():
    t1 = SimpleNamespace(id="t1", status="running")
    t2 = SimpleNamespace(id="t2", status="done")
    return SimpleNamespace(tasks=[t1, t2])


def _wired(trust_score=0.9):
    tr = ReferenceTrustRegistry()
    tr.record(TrustMeta(item_id="i1", author_id="alice", trust_score=trust_score, version=1))
    ir = ReferenceIdentityRegistry()
    ir.register(AgentIdentity(agent_id="agent-1", specialization="general", trust_level=0.8))
    mem = InMemoryProceduralMemory()
    dash = build_default_dashboard(
        kernel=_fake_kernel(), memory_platform=mem, trust_registry=tr,
        identity_registry=ir, task_store=_fake_task_store(),
        model_registry=SimpleNamespace(catalog=lambda: [SimpleNamespace(id="m1"), SimpleNamespace(id="m2")]),
    )
    return dash, tr, ir, mem


# 1) snapshot reflects memory/agents/trust/tasks/kernel-state
def test_snapshot_reflects_state():
    dash, tr, ir, mem = _wired()
    snap = dash.snapshot()
    assert isinstance(snap, DashboardSnapshot)
    assert snap.node_id == "nodeA"
    assert snap.kernel_state == "DELIBERATE"
    assert "agent-1" in snap.agents
    assert ("alice", 0.9) in snap.trust
    assert "m1" in snap.models and "m2" in snap.models
    assert ("t1", "running") in snap.tasks and ("t2", "done") in snap.tasks


# 2) READ-ONLY: snapshot() must not mutate the kernel/trust/memory
def test_read_only_does_not_mutate():
    dash, tr, ir, mem = _wired()
    # capture internal state fingerprints
    trust_before = dict(tr._by_author)
    mem_before = (len(mem.list_skills()), 0, 0)
    # call snapshot multiple times with varied reads
    for _ in range(3):
        dash.snapshot()
    # trust registry untouched (same author keys + scores)
    assert dict(tr._by_author) == trust_before
    # memory unchanged (procedural memory: list_skills count stable)
    assert (len(mem.list_skills()), 0, 0) == mem_before


# 3) determinism (I-09): identical snapshots + stable JSON
def test_determinism():
    dash, _, _, _ = _wired()
    s1 = dash.snapshot()
    s2 = dash.snapshot()
    assert s1 == s2
    assert dash.render_json(s1) == dash.render_json(s2)
    assert dash.render_text(s1) == dash.render_text(s2)


# 4) missing components -> empty surfaces (graceful, still renders)
def test_missing_components_graceful():
    dash = build_default_dashboard(kernel=_fake_kernel())  # nothing else wired
    snap = dash.snapshot()
    assert snap.agents == ()
    assert snap.trust == ()
    assert snap.models == ()
    assert snap.tasks == ()
    assert snap.memory_counts == (0, 0, 0)
    # renderer still works
    assert "node=nodeA" in dash.render_text(snap)
    assert "nodeA" in dash.render_json(snap)


# 5) IDashboard contract satisfied (concrete impl is instantiable + behaves as port)
def test_idashboard_contract():
    dash, _, _, _ = _wired()
    assert isinstance(dash, IDashboard)
    # A real, non-abstract implementation can be constructed and used.
    snap = dash.snapshot()
    assert isinstance(snap, DashboardSnapshot)
    assert dash.render_json(snap)  # renders without error
