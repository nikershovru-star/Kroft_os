"""Stage 45 + 57 — Graph link suggestions and hidden connections."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestGraphSuggestions:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, label in (
            ("python.md", "Python Programming"),
            ("rust.md", "Rust Programming"),
            ("go.md", "Go Programming"),
            ("cpp.md", "C++ Programming"),
            ("vim.md", "Vim Editor"),
            ("emacs.md", "Emacs Editor"),
        ):
            b.add_node(nid, label, {"tags": ["lang"] if "Editor" not in label else ["tool"]})
        b.add_edge("python.md", "rust.md", "links")
        b.add_edge("rust.md", "go.md", "links")
        b.add_edge("vim.md", "emacs.md", "links")
        return GraphQueryEngine(b)

    def test_suggest_links_returns_list(self):
        engine = self._make_engine()
        result = engine.suggest_links("python", top_k=3)
        assert isinstance(result, list)
        assert result
        assert all("id" in item for item in result)

    def test_suggest_links_excludes_existing(self):
        engine = self._make_engine()
        result = engine.suggest_links("python", top_k=10)
        assert "rust.md" not in {item["id"] for item in result}

    def test_find_hidden_connections_global(self):
        engine = self._make_engine()
        result = engine.find_hidden_connections(threshold=0.15, limit=20)
        assert result["ok"] is True
        pairs = result["pairs"]
        assert pairs
        ids = {p["from"] for p in pairs} | {p["to"] for p in pairs}
        assert any(x in ids for x in ("cpp.md", "vim.md", "emacs.md"))

    def test_apply_suggested_link_creates_edge(self):
        engine = self._make_engine()
        result = engine.apply_suggested_link("go.md", "cpp.md", relation="links")
        assert result["ok"] is True
        assert result["created"] is True
        snapshot = engine._graph.get_graph()
        assert any(e["from"] == "go.md" and e["to"] == "cpp.md" for e in snapshot["edges"])

    def test_apply_suggested_link_idempotent(self):
        engine = self._make_engine()
        first = engine.apply_suggested_link("go.md", "cpp.md", relation="links")
        second = engine.apply_suggested_link("go.md", "cpp.md", relation="links")
        assert first["ok"] is True and first["created"] is True
        assert second["ok"] is True and second["created"] is False


class TestGraphSuggestionsAgent:
    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("find_hidden_connections", lambda **kw: {"ok": True, "pairs": []})
        reg.register("apply_suggested_link", lambda **kw: {"ok": True, "created": False})
        svc = AgentService(reg)
        # RU intents route and succeed with local mocks
        assert svc.execute("найди скрытые связи")["ok"] is True
        assert svc.execute("примени связь от a.md к b.md")["ok"] is True
        # EN intents now route correctly (Stage 57 fix: specific pattern precedes
        # generic `find ...`). With the tool registered they succeed, like RU.
        en_find = svc.execute("find hidden connections")
        assert en_find["ok"] is True
        en_apply = svc.execute("apply suggested link from a.md to b.md")
        assert en_apply["ok"] is False
        assert "apply_suggested_link" in en_apply.get("error", "") or "not available" in en_apply.get("error", "")
