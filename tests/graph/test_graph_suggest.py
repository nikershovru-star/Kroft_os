"""Stage 45 — Graph link recommendation tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphSuggest:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, label in (
            ("python.md", "Python"),
            ("budget.md", "Budget"),
            ("notes.md", "Notes"),
            ("ml.md", "Machine Learning"),
            ("cpp.md", "C Plus Plus"),
        ):
            b.add_node(nid, label, {})
        # python linked to budget and notes; ml linked to python; cpp isolated
        b.add_edge("python.md", "budget.md", "links")
        b.add_edge("python.md", "notes.md", "links")
        b.add_edge("ml.md", "python.md", "links")
        return GraphQueryEngine(b)

    def test_suggest_excludes_existing(self):
        engine = self._make_engine()
        # python already linked to budget and notes (and ml->python, but not python->ml)
        sug = engine.suggest_links("python", top_k=10)
        targets = {s["id"] for s in sug}
        # existing outgoing from python: budget, notes
        assert "budget.md" not in targets
        assert "notes.md" not in targets
        # self excluded
        assert "python.md" not in targets

    def test_suggest_prioritizes_graph_proximity(self):
        engine = self._make_engine()
        # ml is neighbor of python (ml->python). python and ml share neighbor context.
        # cpp is isolated. ml should rank higher than cpp.
        sug = engine.suggest_links("python", top_k=10)
        ids = [s["id"] for s in sug]
        assert "ml.md" in ids
        # ml should appear before cpp because of graph proximity
        assert ids.index("ml.md") < ids.index("cpp.md")

    def test_suggest_content_overlap(self):
        engine = self._make_engine()
        # "Machine Learning" shares word "learning"? No, but title token overlap
        # between python and ml is higher than python and cpp (zero).
        sug = engine.suggest_links("python", top_k=10)
        ml_score = next(s["score"] for s in sug if s["id"] == "ml.md")
        cpp_score = next(s["score"] for s in sug if s["id"] == "cpp.md")
        assert ml_score > cpp_score

    def test_suggest_empty_for_unknown(self):
        engine = self._make_engine()
        assert engine.suggest_links("nonexistent xyz") == []

    def test_agent_suggest_intent(self):
        r = ToolRegistry()
        r.register("graph_suggest", lambda query, top_k=5: {
            "ok": True, "suggestions": [{"id": "ml.md", "score": 0.5}]
        })
        svc = AgentService(r)
        res = svc.execute("suggest links for python")
        assert res["tool"] == "graph_suggest"
        assert res["result"]["ok"] is True
        assert any(s["id"] == "ml.md" for s in res["result"]["suggestions"])
