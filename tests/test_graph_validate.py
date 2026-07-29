"""Stage 49 — Graph validation & auto-fix tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path: str, data: str) -> None:
        self._files[path] = data


class TestGraphValidate:
    def _make_engine(self, fs=None, path=None):
        b = InMemoryGraphBuilder()
        for nid in ("a.md", "b.md", "c.md", "d.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("a.md", "b.md", "links")
        b.add_edge("b.md", "c.md", "links")
        # d.md is orphan and untagged
        # broken link: a.md -> missing.md
        b.add_edge("a.md", "missing.md", "links")
        return GraphQueryEngine(b, fs=fs, snapshot_path=path)

    def test_validate_finds_all_issues(self):
        engine = self._make_engine()
        r = engine.validate_graph()
        assert r["ok"] is True
        types = {i["type"] for i in r["issues"]}
        assert "orphan" in types
        assert "no_tags" in types
        assert "broken_link" in types

    def test_find_broken_links(self):
        engine = self._make_engine()
        broken = engine.find_broken_links()
        assert len(broken) == 1
        assert broken[0]["to"] == "missing.md"

    def test_fix_graph_removes_broken_and_tags(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, path="g.json")
        r = engine.fix_graph()
        assert r["ok"] is True
        assert r["fixes"]["broken_removed"] == 1
        assert r["fixes"]["orphans_tagged"] == 1  # d.md
        assert r["fixes"]["untagged_tagged"] >= 1
        # broken link gone
        snap = engine._graph.get_graph()
        assert not any(e["to"] == "missing.md" for e in snap["edges"])
        # snapshot written because fix applied
        assert "g.json" in fs._files

    def test_validate_after_fix_is_cleaner(self):
        engine = self._make_engine()
        engine.fix_graph()
        r = engine.validate_graph()
        assert not any(i["type"] == "broken_link" for i in r["issues"])

    def test_agent_validate_intent(self):
        r = ToolRegistry()
        r.register("validate_graph", lambda: {"ok": True, "issues": []})
        svc = AgentService(r)
        res = svc.execute("validate graph")
        assert res["tool"] == "validate_graph"
        assert res["result"]["ok"] is True
