"""Stage 58 — graph query DSL."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine


def _build_engine():
    builder = InMemoryGraphBuilder()
    builder.add_node("python.md", "Python Programming", {"tags": ["lang"], "type": "lang"})
    builder.add_node("rust.md", "Rust Programming", {"tags": ["lang"], "type": "lang"})
    builder.add_node("go.md", "Go Programming", {"tags": ["lang"], "type": "lang"})
    builder.add_node("vim.md", "Vim Editor", {"tags": ["tool"], "type": "tool"})
    builder.add_edge("python.md", "rust.md", "links")
    builder.add_edge("rust.md", "go.md", "links")
    builder.add_edge("vim.md", "emacs.md", "links")
    return GraphQueryEngine(builder)


class TestGraphQueryDSL:
    def test_match_nodes_by_tag(self):
        engine = _build_engine()
        result = engine.query_dsl('MATCH (n:lang) RETURN n.id')
        assert result["ok"] is True
        assert result["query_type"] == "match"
        ids = [row["n.id"] for row in result["results"]]
        assert "python.md" in ids
        assert "vim.md" not in ids

    def test_match_edges_by_relation(self):
        engine = _build_engine()
        result = engine.query_dsl('MATCH (a)-[e]->(b) WHERE e.relation = "links" RETURN a, b')
        assert result["ok"] is True
        assert result["count"] >= 2  # builder inserts autobound edges
        pairs = {(row["a"], row["b"]) for row in result["results"]}
        assert ("python.md", "rust.md") in pairs

    def test_path_query(self):
        engine = _build_engine()
        result = engine.query_dsl('PATH FROM python.md TO go.md MAX 3')
        assert result["ok"] is True
        assert result["query_type"] == "path"
        assert len(result["results"]) == 1
        assert result["results"][0]["nodes"] == ["python.md", "rust.md", "go.md"]

    def test_health_query(self):
        engine = _build_engine()
        result = engine.query_dsl("HEALTH")
        assert result["ok"] is True
        assert result["query_type"] == "health"
        assert "orphan_count" in result

    def test_notifications_query(self):
        engine = _build_engine()
        engine.check_and_notify()
        result = engine.query_dsl("NOTIFICATIONS PENDING")
        assert result["ok"] is True
        assert result["query_type"] == "notifications"
        assert isinstance(result["results"], list)

    def test_agent_intents(self):
        from services import AgentService, ToolRegistry
        reg = ToolRegistry()
        reg.register("query_dsl", lambda **kw: {"ok": True, "tool": "query_dsl"})
        svc = AgentService(reg)
        out = svc.execute("query graph: MATCH (n) RETURN n.id")
        assert out["tool"] == "query_dsl"
        out = svc.execute("граф запрос: HEALTH")
        assert out["tool"] == "query_dsl"
