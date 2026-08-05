"""Stage 53 — Graph-Based Agent Context Memory tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def write_content(self, path, data):
        pass


class TestGraphContextMemory:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, title in (
            ("python.md", "Python"),
            ("rust.md", "Rust"),
            ("go.md", "Go"),
        ):
            b.add_node(nid, title, {"tags": ["lang"]})
        b.add_edge("python.md", "rust.md", "links")
        b.add_edge("rust.md", "go.md", "links")
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="graph_snapshot.json")

    def test_record_user_query_creates_session_subgraph(self):
        engine = self._make_engine()
        r = engine.record_user_query("sess-1", "tell me about python", ["python.md"], intent="search")
        assert r["ok"] is True
        assert r["hits_recorded"] == 1
        assert r["interests_updated"] == 1

        snap = engine._graph.get_graph()
        session_node = next((n for n in snap["nodes"] if n["id"] == "session:sess-1"), None)
        assert session_node is not None
        assert session_node["meta"]["type"] == "session"

    def test_get_session_context_returns_queries_and_interests(self):
        engine = self._make_engine()
        engine.record_user_query("sess-2", "python vs rust", ["python.md", "rust.md"])
        ctx = engine.get_session_context("sess-2", depth=2)
        assert ctx["ok"] is True
        assert len(ctx["recent_queries"]) == 1
        assert ctx["recent_queries"][0]["text"] == "python vs rust"
        assert len(ctx["interest_profile"]) == 2
        assert {i["node"] for i in ctx["interest_profile"]} == {"python.md", "rust.md"}

    def test_suggest_next_returns_related_unvisited_nodes(self):
        engine = self._make_engine()
        engine.record_user_query("sess-3", "python info", ["python.md"])
        engine.record_user_query("sess-3", "rust info", ["rust.md"])
        sug = engine.suggest_next("sess-3", top_n=3)
        assert sug["ok"] is True
        assert any(s["node"] == "go.md" for s in sug["suggestions"])

    def test_interest_weights_accumulate(self):
        engine = self._make_engine()
        engine.record_user_query("sess-4", "python again", ["python.md"])
        engine.record_user_query("sess-4", "python once more", ["python.md"])
        ctx = engine.get_session_context("sess-4")
        python_interest = next(i for i in ctx["interest_profile"] if i["node"] == "python.md")
        assert python_interest["weight"] == 2

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("record_user_query", lambda **kw: {"ok": True})
        reg.register("get_session_context", lambda **kw: {"ok": True})
        reg.register("suggest_next", lambda **kw: {"ok": True})
        reg.register("get_personalized_summary", lambda **kw: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("remember that I like python")["tool"] == "record_user_query"
        assert svc.execute("what do you know about my interests")["tool"] == "get_session_context"
        assert svc.execute("suggest something")["tool"] == "suggest_next"
        assert svc.execute("запомни что я люблю rust")["tool"] == "record_user_query"
        assert svc.execute("что посоветуешь")["tool"] == "suggest_next"
