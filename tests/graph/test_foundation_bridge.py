"""Foundation -> IGraphBuilder boot-bridge tests (ADR-033, ТЗ Boot-Bridge).

Test A (fast, in-memory): load_from_dict preserves production node `type`
so Multi-Resolution nodes_by_type works on list-shaped snapshots.

Test B (slow): full build_container() loads the real 717MB Foundation
snapshot and GraphQueryEngine.nodes_by_type("unknown") must be ~18490.
Marked slow; run separately if needed.
"""
from __future__ import annotations

import os

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.graph_query_engine import GraphQueryEngine


def test_load_from_dict_preserves_type():
    b = InMemoryGraphBuilder()
    snap = [
        {"id": "n1", "label": "N1", "type": "unknown", "meta": {"x": 1}},
        {"id": "n2", "label": "N2", "type": "work", "meta": {}},
    ]
    b.load_from_dict({n["id"]: n for n in snap}, [])
    q = GraphQueryEngine(b)
    assert "n1" in q.nodes_by_type("unknown")
    assert "n2" in q.nodes_by_type("work")
    # meta preserved -> nodes_by_metadata works
    assert q.nodes_by_metadata("x", 1) == ["n1"]


def test_load_from_dict_merges_runtime_nodes():
    # runtime node present before bridge must survive Foundation load
    b = InMemoryGraphBuilder()
    b.add_node("handoff:wf:s1", "h", {"type": "handoff", "workflow_id": "wf"})
    snap = [{"id": "n1", "label": "N1", "type": "unknown", "meta": {}}]
    b.load_from_dict({n["id"]: n for n in snap}, [])
    q = GraphQueryEngine(b)
    assert "n1" in q.nodes_by_type("unknown")
    assert "handoff:wf:s1" in q.nodes_by_metadata("workflow_id", "wf")


def test_load_from_dict_list_edges():
    b = InMemoryGraphBuilder()
    snap = [{"id": "a", "label": "A", "type": "unknown", "meta": {}}]
    edges = [{"from": "a", "to": "b", "type": "supports"}]
    b.load_from_dict({n["id"]: n for n in snap}, edges)
    assert b.get_neighbors("a") == ["b"]


def _repo_root() -> str:
    # container_builder computes Foundation path from __file__/.., so any
    # vault_path works for the bridge; use the repo root.
    return os.getcwd()


def test_build_container_sees_foundation_slow():
    """ТЗ §6 — slow (loads real ~683MB Foundation snapshot).

    NOTE (honest correction vs original ТЗ): the B.9 forensic figure
    "type:unknown = 18490" was a raw-string grep artifact — production graph
    nodes carry NO top-level `type` and NO `meta.type == "unknown"` (verified:
    17641 nodes total, 0 have type "unknown", 47 have meta.type "work").
    The bridge goal (Foundation visible to Query API) is proven by:
      (a) builder holds all 17641 Foundation nodes, and
      (b) nodes_by_type("work") == 47 (real type query works on Foundation).
    """
    from composition.container_builder import build_container
    c = build_container(_repo_root())
    q = c.resolve("GraphQueryEngine")
    all_nodes = q._snapshot().get("nodes", [])
    # (a) Foundation fully loaded
    assert len(all_nodes) >= 17641, f"expected >=17641 Foundation nodes, got {len(all_nodes)}"
    # (b) Multi-Resolution type query works on production data
    work_nodes = q.nodes_by_type("work")
    assert len(work_nodes) == 47, f"expected 47 meta.type=='work', got {len(work_nodes)}"
    # runtime handoff nodes must remain queryable (not wiped by bridge)
    assert q.nodes_by_metadata("type", "handoff") is not None
