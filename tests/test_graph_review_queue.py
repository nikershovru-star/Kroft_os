"""Stage 51 — Graph-driven review queue & compound query tests."""
from __future__ import annotations

import time

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestReviewQueue:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid in ("a.md", "b.md", "c.md", "d.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("a.md", "b.md", "links")
        b.add_edge("b.md", "c.md", "links")
        # d.md is orphan and untagged; a/b/c have no tags either in base setup
        return GraphQueryEngine(b)

    def test_review_queue_prioritizes_orphans(self):
        engine = self._make_engine()
        q = engine.review_queue(top_k=10)
        assert q[0]["id"] == "d.md"  # orphan + untagged + peripheral
        assert "orphan" in q[0]["reasons"]
        assert any("link" in a for a in q[0]["actions"])

    def test_review_queue_returns_explainable_scores(self):
        engine = self._make_engine()
        q = engine.review_queue(top_k=3)
        for item in q:
            assert "priority" in item
            assert isinstance(item["reasons"], list)
            assert isinstance(item["actions"], list)

    def test_compound_query_orphans(self):
        engine = self._make_engine()
        res = engine.compound_query(orphan=True)
        assert len(res) == 1
        assert res[0]["id"] == "d.md"
        assert res[0]["matches"]["orphan"] is True

    def test_compound_query_tags_and_degree(self):
        engine = self._make_engine()
        engine.add_tag("a", "important")
        engine.add_tag("b", "important")
        res = engine.compound_query(tags=["important"], min_degree=1)
        ids = {r["id"] for r in res}
        assert "a.md" in ids
        assert "b.md" in ids
        assert "d.md" not in ids  # degree 0

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("review_queue", lambda top_k=10: {"ok": True, "queue": [{"id": "x.md"}]})
        reg.register("compound_query", lambda **kw: {"ok": True, "matches": []})
        svc = AgentService(reg)
        assert svc.execute("review queue")["tool"] == "review_queue"
        assert svc.execute("что почитать")["tool"] == "review_queue"
        assert svc.execute("show orphans")["tool"] == "compound_query"
        assert svc.execute("покажи сирот")["tool"] == "compound_query"
