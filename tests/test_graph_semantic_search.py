"""Stage 59 — Graph Semantic Search (TF-IDF) tests."""
from __future__ import annotations

import pytest
from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self):
        self._files = {}
    def write_content(self, path, data):
        self._files[path] = data


class TestGraphSemanticSearch:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid, title in (
            ("python.md", "Python Programming Language"),
            ("rust.md", "Rust Systems Programming"),
            ("go.md", "Go Programming Language"),
            ("vim.md", "Vim Text Editor"),
            ("emacs.md", "Emacs Text Editor"),
        ):
            b.add_node(nid, title, {"tags": ["lang"] if "Editor" not in title else ["tool"]})
        b.add_edge("python.md", "rust.md", "links")
        b.add_edge("rust.md", "go.md", "links")
        b.add_edge("vim.md", "emacs.md", "links")
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="g.json")

    def test_rebuild_semantic_index(self):
        engine = self._make_engine()
        r = engine.rebuild_semantic_index()
        assert r["ok"] is True
        assert r["documents"] == 5

    def test_semantic_search_finds_programming_languages(self):
        engine = self._make_engine()
        r = engine.semantic_search("programming language", top_k=3)
        assert isinstance(r, list)
        ids = [res[0] for res in r]
        assert "python.md" in ids or "go.md" in ids
        assert "vim.md" not in ids[:2]

    def test_semantic_search_boosts_session_interest(self):
        engine = self._make_engine()
        engine.record_user_query("sess-59", "python info", ["python.md"])
        engine.record_user_query("sess-59", "python again", ["python.md"])
        r = engine.semantic_search("programming", top_k=3)
        assert isinstance(r, list)
        assert r and r[0][0] == "python.md"

    def test_semantic_similarity(self):
        engine = self._make_engine()
        sim = engine.semantic_similarity("python.md", "go.md")
        assert 0.0 <= sim <= 1.0
        sim2 = engine.semantic_similarity("python.md", "vim.md")
        assert sim > sim2

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("semantic_search", lambda **kw: {"ok": True})
        reg.register("semantic_similarity", lambda **kw: {"ok": True})
        reg.register("rebuild_semantic_index", lambda **kw: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("semantic search programming language")["tool"] == "semantic_search"
        assert svc.execute("how similar are python.md and go.md")["tool"] == "semantic_similarity"
        assert svc.execute("поиск по смыслу язык программирования")["tool"] == "semantic_search"
        assert svc.execute("перестрой семантический индекс")["tool"] == "rebuild_semantic_index"
