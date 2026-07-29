"""Stage 54 — Graph Health Monitor tests."""
from __future__ import annotations

import pytest
from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self):
        self._files = {}
    def write_content(self, path, data):
        self._files[path] = data


class TestGraphHealthMonitor:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, title in (
            ("python.md", "Python"),
            ("rust.md", "Rust"),
            ("go.md", "Go"),
            ("python-copy.md", "Python"),  # duplicate title
            ("orphan.md", "Orphan"),       # isolated
        ):
            b.add_node(nid, title, {"tags": ["lang"] if nid != "orphan.md" else []})
        b.add_edge("python.md", "rust.md", "links")
        b.add_edge("rust.md", "go.md", "links")
        b.add_edge("go.md", "missing.md", "links")  # broken
        b.add_edge("python-copy.md", "python.md", "links")  # link duplicate so it's not an orphan
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="g.json")

    def test_graph_health_report(self):
        engine = self._make_engine()
        r = engine.graph_health_report()
        assert r["ok"] is True
        assert "orphan.md" in r["orphans"]
        assert r["orphan_count"] == 1
        assert r["broken_count"] == 1
        assert r["clusters"] >= 1
        assert 0.0 <= r["density"] <= 1.0

    def test_find_duplicate_candidates(self):
        engine = self._make_engine()
        r = engine.find_duplicate_candidates(threshold=0.8)
        assert r["ok"] is True
        pairs = [tuple(sorted((c["from"], c["to"]))) for c in r["candidates"]]
        assert ("python-copy.md", "python.md") in pairs
        assert any(c["score"] >= 0.8 for c in r["candidates"])

    def test_cleanup_orphans(self):
        engine = self._make_engine()
        # dry run
        r = engine.cleanup_orphans(dry_run=True)
        assert r["removed"] == 0
        assert "orphan.md" in {n["id"] for n in engine._graph._nodes.values()}
        # real cleanup
        r = engine.cleanup_orphans(dry_run=False)
        assert r["removed"] == 1
        assert "orphan.md" not in {n["id"] for n in engine._graph._nodes.values()}

    def test_merge_nodes(self):
        engine = self._make_engine()
        r = engine.merge_nodes("python-copy.md", "python.md", dry_run=False)
        assert r["ok"] is True
        snap = engine._graph.get_graph()
        ids = {n["id"] for n in snap["nodes"]}
        assert "python-copy.md" not in ids
        assert "python.md" in ids
        for e in snap["edges"]:
            assert e.get("from") != "python-copy.md"
            assert e.get("to") != "python-copy.md"

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("graph_health_report", lambda **kw: {"ok": True})
        reg.register("find_duplicate_candidates", lambda **kw: {"ok": True})
        reg.register("cleanup_orphans", lambda **kw: {"ok": True})
        reg.register("merge_nodes", lambda **kw: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("graph health report")["tool"] == "graph_health_report"
        assert svc.execute("find duplicates")["tool"] == "find_duplicate_candidates"
        assert svc.execute("cleanup orphans")["tool"] == "cleanup_orphans"
        assert svc.execute("merge python-copy.md into python.md")["tool"] == "merge_nodes"
        assert svc.execute("полный отчёт о графе")["tool"] == "graph_health_report"
