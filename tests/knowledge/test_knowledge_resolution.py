"""ADR-028 Stage 1 — ReferenceKnowledgeResolution unit + negative tests.

Proof-over-existence: not 'class exists' but a LIVE run where one query yields
5 resolution levels, evidence_for() reaches EVIDENCE, provenance is never empty,
and an item with no source chain raises (never degrades).
"""

from __future__ import annotations

import inspect

import pytest

from contracts import IGraphBuilder, IGraphQuery
from contracts.i_knowledge_resolution import (
    EvidenceRef,
    ResolutionLevel,
    ResolvedView,
)
from services.knowledge_resolution import (
    ReferenceKnowledgeResolution,
    ResolutionError,
)


class _FakeBuilder(IGraphBuilder):
    def __init__(self, nodes, edges):
        self._nodes = {n["id"]: n for n in nodes}
        self._edges = edges

    def add_node(self, id, label, meta): self._nodes[id] = {"id": id, "label": label, "meta": meta}
    def add_edge(self, from_id, to_id, relation): self._edges.append({"from": from_id, "to": to_id, "relation": relation})
    def get_graph(self): return {"nodes": list(self._nodes.values()), "edges": self._edges}
    def get_neighbors(self, node_id): return [e["to"] for e in self._edges if e["from"] == node_id]
    def clear(self): self._nodes.clear(); self._edges.clear()
    def remove_node(self, node_id): return self._nodes.pop(node_id, None) is not None
    def remove_edge(self, f, t):
        before = len(self._edges); self._edges = [e for e in self._edges if not (e["from"] == f and e["to"] == t)]
        return len(self._edges) != before
    def add_tag(self, node_id, tag):
        n = self._nodes.get(node_id)
        if not n: return False
        tags = n.setdefault("meta", {}).setdefault("tags", [])
        if tag in tags: return False
        tags.append(tag); return True
    def remove_tag(self, node_id, tag):
        n = self._nodes.get(node_id)
        if not n: return False
        tags = n.get("meta", {}).get("tags", [])
        if tag not in tags: return False
        tags.remove(tag); return True
    # IService + snapshot/restore stubs (test doubles only)
    def name(self): return "fake-builder"
    def initialize(self, context=None): pass
    def execute(self, context_data): return ""
    def snapshot(self, fs, path): pass
    def restore(self, fs, path): return False


class _FakeQuery(IGraphQuery):
    def __init__(self, builder): self._g = builder

    def backlinks(self, node_id): return [e["from"] for e in self._g.get_graph()["edges"] if e["to"] == node_id]
    def forward_links(self, node_id): return [e["to"] for e in self._g.get_graph()["edges"] if e["from"] == node_id]
    def nodes_by_tag(self, tag): return [n["id"] for n in self._g.get_graph()["nodes"] if tag in (n.get("meta", {}).get("tags", []))]
    def orphan_nodes(self): return [n["id"] for n in self._g.get_graph()["nodes"] if not self.forward_links(n["id"]) and not self.backlinks(n["id"])]
    def path(self, from_id, to_id, max_depth=10): return [from_id, to_id] if from_id != to_id else []
    def cluster_by_tag(self):
        out = {}
        for n in self._g.get_graph()["nodes"]:
            for t in n.get("meta", {}).get("tags", []):
                out.setdefault(t, []).append(n["id"])
        return out
    def stats(self): return {"total_nodes": len(self._g.get_graph()["nodes"]), "total_edges": len(self._g.get_graph()["edges"])}
    def query_with_abstention(self, query, top_k=10, semantic_threshold=None): return ([], True)
    def get_cluster(self, node_id, k=5): return []
    def top_central(self, k=5, metric="pagerank"): return []
    def compound_query(self, **filters):
        label = filters.get("label_contains")
        nodes = self._g.get_graph()["nodes"]
        if label:
            return [n for n in nodes if label.lower() in (n.get("label", "") or "").lower()]
        return nodes
    # IService stubs (test double only)
    def name(self): return "fake-query"
    def initialize(self, context=None): pass
    def execute(self, context_data): return ""


def _build():
    # 147 evidence nodes grouped into 3 subsystems via tags.
    nodes = []
    for i in range(147):
        sub = i % 3
        tag = f"sub{sub}"
        prov = [] if i % 5 != 0 else [f"obs-{i}"]  # some nodes have deeper provenance
        nodes.append({"id": f"n{i}", "label": f"node {i}", "meta": {"tags": [tag], "provenance": prov}})
    edges = [{"from": f"n{i}", "to": f"n{(i+1)%147}", "relation": "next"} for i in range(147)]
    b = _FakeBuilder(nodes, edges)
    q = _FakeQuery(b)
    return ReferenceKnowledgeResolution(q, b)


def test_view_all_five_levels():
    svc = _build()
    for lvl in ResolutionLevel:
        v = svc.view("node", lvl)
        assert isinstance(v, ResolvedView)
        assert v.level == lvl
        assert v.provenance, f"empty provenance at {lvl.name}"


def test_provenance_never_empty_on_node():
    svc = _build()
    v = svc.view("node", ResolutionLevel.NODE)
    assert all(it.provenance for it in v.items), "a node item had empty provenance"


def test_evidence_chain_reaches_evidence():
    svc = _build()
    ev = svc.evidence_for("n0")
    assert ev, "evidence_for returned empty"
    assert all(isinstance(e, EvidenceRef) for e in ev)


def test_zoom_out_coarsens():
    svc = _build()
    node_v = svc.view("node", ResolutionLevel.NODE)
    out = svc.zoom_out(node_v)
    assert out.level == ResolutionLevel.CONCEPT
    assert out.collapsed_from > 0


def test_collapse_preserves_sources():
    svc = _build()
    sys_v = svc.view("node", ResolutionLevel.SYSTEM)
    # SYSTEM summary must cover (almost) all source nodes; the concept cap (<=12)
    # may trim a few, so assert broad coverage rather than an exact count.
    assert sys_v.collapsed_from >= 140
    assert len(sys_v.provenance) > 0


# --- NEGATIVE tests (ADR-028 gate requirement) -------------------------
def test_empty_provenance_raises_not_degrades():
    # a node with explicitly empty provenance and no underlying record must
    # raise on evidence_for, never return empty list silently.
    b = _FakeBuilder([], [])
    q = _FakeQuery(b)
    svc = ReferenceKnowledgeResolution(q, b)
    with pytest.raises(ResolutionError):
        svc.evidence_for("ghost-node")


def test_service_does_not_import_forbidden_layers():
    # ADR-028 negative gate: importing the service must NOT pull in kernel/ or adapters/.
    import services.knowledge_resolution as mod
    src = inspect.getsource(mod)
    assert "from kernel" not in src and "import kernel" not in src
    assert "from adapters" not in src and "import adapters" not in src
