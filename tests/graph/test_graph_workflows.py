"""Stage 52 — Graph-driven agent workflow tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphWorkflows:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, label in (
            ("python.md", "Python"),
            ("ml.md", "Machine Learning"),
            ("budget.md", "Budget"),
            ("pytorch.md", "PyTorch"),
            ("data.md", "Data Science"),
        ):
            b.add_node(nid, label, {})
        b.add_edge("python.md", "ml.md", "links")
        b.add_edge("python.md", "budget.md", "links")
        b.add_edge("pytorch.md", "python.md", "links")
        b.add_edge("ml.md", "data.md", "links")
        return GraphQueryEngine(b)

    def test_research_topic_returns_structure(self):
        engine = self._make_engine()
        r = engine.research_topic("python", depth=1)
        assert r["ok"] is True
        assert r["seed"] == "python.md"
        assert "neighbors" in r
        assert "lateral" in r
        assert "gaps" in r
        assert "suggested_links" in r
        assert isinstance(r["plan"], list)

    def test_research_topic_seed_not_found(self):
        engine = self._make_engine()
        r = engine.research_topic("nonexistent", depth=1)
        assert r["ok"] is False
        assert r["error"] == "seed not found"

    def test_bridge_topics_connected(self):
        engine = self._make_engine()
        r = engine.bridge_topics("pytorch", "ml")
        assert r["ok"] is True
        assert r["connected"] is True
        assert "python.md" in r["path"]
        assert r["length"] >= 1

    def test_bridge_topics_disconnected(self):
        engine = self._make_engine()
        # Add a disconnected island node with no edges.
        b = InMemoryGraphBuilder()
        for nid, label in (
            ("alpha.md", "Alpha"),
            ("beta.md", "Beta"),
            ("gamma.md", "Gamma"),
        ):
            b.add_node(nid, label, {})
        b.add_edge("alpha.md", "gamma.md", "links")
        isolated = GraphQueryEngine(b)
        r = isolated.bridge_topics("alpha", "beta")
        assert r["ok"] is True
        assert r["connected"] is False
        assert r["path"] is None
        assert isinstance(r["plan"], list)

    def test_expand_knowledge_returns_targets(self):
        engine = self._make_engine()
        r = engine.expand_knowledge("python", top_k=3)
        assert r["ok"] is True
        assert "cluster" in r
        assert "expansion_targets" in r
        assert isinstance(r["plan"], list)

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("research_topic", lambda query: {"ok": True, "seed": query})
        reg.register("bridge_topics", lambda from_query, to_query: {"ok": True})
        reg.register("expand_knowledge", lambda query: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("research python")["tool"] == "research_topic"
        assert svc.execute("bridge pytorch and ml")["tool"] == "bridge_topics"
        assert svc.execute("expand python")["tool"] == "expand_knowledge"
        assert svc.execute("исследовать питон")["tool"] == "research_topic"
        assert svc.execute("соединить питон и бюджет")["tool"] == "bridge_topics"
