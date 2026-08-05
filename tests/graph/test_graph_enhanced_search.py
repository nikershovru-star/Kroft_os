"""Stage 48 — Graph-enhanced hybrid search ranking tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphEnhancedSearch:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, label in (
            ("python.md", "Python"),
            ("ml.md", "Machine Learning"),
            ("budget.md", "Budget"),
            ("pytorch.md", "PyTorch"),
        ):
            b.add_node(nid, label, {})
        # python linked to ml; pytorch isolated
        b.add_edge("python.md", "ml.md", "links")
        return GraphQueryEngine(b)

    def _mock_hybrid(self, engine, scores: dict):
        def _fn(query, top_k):
            items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            return items[:top_k]
        engine.hybrid_search = _fn

    def test_graph_boosts_neighbor(self):
        """ml.md is neighbor of python.md (semantic 0.1). Graph boost should lift it above budget.md (0.3)."""
        engine = self._make_engine()
        self._mock_hybrid(engine, {
            "python.md": 0.9,
            "pytorch.md": 0.5,
            "budget.md": 0.3,
            "ml.md": 0.1,
        })
        res = engine.graph_enhanced_search("python", top_k=4, alpha=0.5, beta=0.4, gamma=0.1)
        ids = [r["id"] for r in res]
        assert "ml.md" in ids
        assert ids.index("ml.md") < ids.index("budget.md")

    def test_graph_enhanced_explainable(self):
        engine = self._make_engine()
        self._mock_hybrid(engine, {"python.md": 0.9, "ml.md": 0.1})
        res = engine.graph_enhanced_search("py", top_k=2)
        assert len(res) == 2
        for r in res:
            assert "semantic_score" in r
            assert "graph_score" in r
            assert "recency_score" in r
            assert "final_score" in r
            assert "reason" in r
            assert "title" in r

    def test_beta_zero_falls_back_to_semantic(self):
        """With beta=0 order should match pure semantic ranking."""
        engine = self._make_engine()
        self._mock_hybrid(engine, {
            "python.md": 0.9,
            "pytorch.md": 0.5,
            "budget.md": 0.3,
            "ml.md": 0.1,
        })
        res = engine.graph_enhanced_search("py", top_k=4, alpha=1.0, beta=0.0, gamma=0.0)
        ids = [r["id"] for r in res]
        assert ids == ["python.md", "pytorch.md", "budget.md", "ml.md"]

    def test_empty_hybrid_returns_empty(self):
        engine = self._make_engine()
        self._mock_hybrid(engine, {})
        assert engine.graph_enhanced_search("xyz") == []

    def test_agent_hybrid_search_intent(self):
        r = ToolRegistry()
        r.register("enhanced_search", lambda query: {
            "ok": True, "results": [{"id": "a.md", "final_score": 0.9}]
        })
        svc = AgentService(r)
        res = svc.execute("hybrid search python")
        assert res["tool"] == "enhanced_search"
        assert res["result"]["ok"] is True
