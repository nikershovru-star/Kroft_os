"""Stage 46 — Agent graph analytics & health NL-intent tests (5).

NOTE: tests/test_graph_analytics.py is already owned by Stage 26 (graph
analytics engine methods + /api/stats). Stage 46 only ADDS the natural-language
agent interface on top, so its tests live here to avoid clobbering Stage 26.
"""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphAnalytics:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid in ("a.md", "b.md", "c.md", "d.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("a.md", "b.md", "links")
        b.add_edge("b.md", "c.md", "links")
        # d.md is orphan
        return GraphQueryEngine(b)

    def test_graph_stats(self):
        engine = self._make_engine()
        s = engine.graph_stats()
        assert s["nodes"] == 4
        assert s["edges"] == 2
        assert s["orphans"] == 1
        assert "density" in s
        assert 0 <= s["density"] <= 1

    def test_top_central_degree(self):
        engine = self._make_engine()
        top = engine.top_central(k=3, metric="degree")
        # b: out=1 (b->c), in=1 (a->b) → total degree 2
        # a: out=1, in=0 → 1; c: out=0, in=1 → 1; d: 0
        assert top[0]["id"] == "b.md"
        assert len(top) == 3

    def test_top_central_pagerank(self):
        engine = self._make_engine()
        top = engine.top_central(k=2, metric="pagerank")
        assert len(top) == 2
        assert all("score" in x for x in top)

    def test_graph_health(self):
        engine = self._make_engine()
        h = engine.graph_health()
        assert h["ok"] is True
        assert "healthy" in h
        assert h["stats"]["nodes"] == 4

    def test_agent_intents(self):
        r = ToolRegistry()
        r.register("graph_stats", lambda: {"nodes": 4})
        r.register("graph_central", lambda k=5: {"ok": True, "top": [{"id": "b.md"}]})
        svc = AgentService(r)
        assert svc.execute("graph stats")["tool"] == "graph_stats"
        assert svc.execute("most central top 3")["tool"] == "graph_central"
        assert svc.execute("статистика графа")["tool"] == "graph_stats"
        assert svc.execute("самые центральные")["tool"] == "graph_central"
