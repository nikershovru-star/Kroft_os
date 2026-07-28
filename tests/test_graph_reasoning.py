"""Stage 43 - Agent graph-aware reasoning tests (5)."""
from __future__ import annotations

import pytest

from services import AgentService, GraphQueryEngine, ToolRegistry


class TestGraphReasoning:
    def test_neighbors_mock_graph(self):
        engine = GraphQueryEngine.__new__(GraphQueryEngine)
        import networkx as nx

        g = nx.DiGraph()
        g.add_edge("a.md", "b.md")
        g.add_edge("a.md", "c.md")
        g.add_edge("b.md", "d.md")
        engine._g = g
        assert len(engine.get_neighbors("a.md")) == 2
        assert len(engine.get_neighbors("a.md", depth=2)) == 3  # a->b->d

    def test_shortest_path(self):
        engine = GraphQueryEngine.__new__(GraphQueryEngine)
        import networkx as nx

        g = nx.DiGraph()
        g.add_edge("a.md", "b.md")
        g.add_edge("b.md", "c.md")
        engine._g = g
        assert engine.shortest_path("a.md", "c.md") == ["a.md", "b.md", "c.md"]

    def test_no_path(self):
        engine = GraphQueryEngine.__new__(GraphQueryEngine)
        import networkx as nx

        g = nx.DiGraph()
        g.add_nodes_from(["x.md", "y.md"])
        engine._g = g
        assert engine.shortest_path("x.md", "y.md") == []

    def test_agent_neighbors_intent(self):
        r = ToolRegistry()
        r.register(
            "graph_neighbors",
            lambda query, direction="both", depth=1: {"ok": True, "neighbors": [{"id": "b.md"}]},
        )
        svc = AgentService(r)
        res = svc.execute("neighbors of python")
        assert res["tool"] == "graph_neighbors"
        assert res["result"]["ok"] is True

    def test_agent_path_intent(self):
        r = ToolRegistry()
        r.register(
            "graph_path",
            lambda from_query, to_query: {"ok": True, "path": ["a.md", "b.md"]},
        )
        svc = AgentService(r)
        res = svc.execute("path from python to budget")
        assert res["tool"] == "graph_path"
        assert res["result"]["path"] == ["a.md", "b.md"]
