"""Stage 44 — Agent graph mutation tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphMutations:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid in ("a.md", "b.md", "c.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("a.md", "b.md", "links")
        return GraphQueryEngine(b), b

    def test_add_link_idempotent(self):
        engine, builder = self._make_engine()
        # a→c ещё нет
        r = engine.add_link("a", "c")
        assert r["ok"] is True and r["created"] is True
        snap = builder.get_graph()
        assert any(e["from"] == "a.md" and e["to"] == "c.md" for e in snap["edges"])
        # повторно — не дублирует
        r2 = engine.add_link("a", "c")
        assert r2["ok"] is True and r2["created"] is False

    def test_remove_link(self):
        engine, builder = self._make_engine()
        r = engine.remove_link("a", "b")
        assert r["ok"] is True and r["removed"] is True
        snap = builder.get_graph()
        assert not any(e["from"] == "a.md" and e["to"] == "b.md" for e in snap["edges"])
        # повторно — removed=False
        assert engine.remove_link("a", "b")["removed"] is False

    def test_tag_roundtrip(self):
        engine, _ = self._make_engine()
        r1 = engine.add_tag("a", "urgent")
        assert r1["ok"] is True and r1["added"] is True
        r2 = engine.remove_tag("a", "urgent")
        assert r2["ok"] is True and r2["removed"] is True
        r3 = engine.remove_tag("a", "urgent")
        assert r3["removed"] is False

    def test_agent_link_intent(self):
        r = ToolRegistry()
        calls = []
        r.register("graph_link", lambda **kw: calls.append(kw) or {"ok": True, "created": True})
        svc = AgentService(r)
        res = svc.execute("link python to budget")
        assert res["tool"] == "graph_link"
        assert res["result"]["ok"] is True

    def test_agent_tag_intent_ru(self):
        r = ToolRegistry()
        r.register("graph_tag", lambda query, tag: {"ok": True, "node": query, "tag": tag})
        svc = AgentService(r)
        res = svc.execute("тег питон важно")
        assert res["tool"] == "graph_tag"
        assert res["result"]["tag"] == "важно"
