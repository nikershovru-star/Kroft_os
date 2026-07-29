"""Stage 47 — Graph snapshot persistence tests."""
from __future__ import annotations

import json
import os

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    """Duck-typed IFileSystem for tests."""
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path: str, data: str) -> None:
        self._files[path] = data

    def read_content(self, path: str):
        return self._files.get(path)

    def rename(self, old: str, new: str) -> None:
        self._files[new] = self._files.pop(old)


class TestGraphSnapshot:
    def _make_engine(self, fs=None, snapshot_path=None):
        b = InMemoryGraphBuilder()
        for nid in ("python.md", "budget.md", "notes.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("python.md", "budget.md", "links")
        return GraphQueryEngine(b, fs=fs, snapshot_path=snapshot_path)

    def test_auto_snapshot_after_add_link(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, snapshot_path=".kos/graph.json")
        assert engine.auto_snapshot_status()["enabled"] is True
        engine.add_link("python", "notes")
        assert ".kos/graph.json" in fs._files
        payload = json.loads(fs._files[".kos/graph.json"])
        assert any(e["from"] == "python.md" and e["to"] == "notes.md" for e in payload["edges"])

    def test_no_snapshot_when_auto_off(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, snapshot_path=".kos/graph.json")
        engine.set_auto_snapshot(False)
        assert engine.auto_snapshot_status()["enabled"] is False
        engine.add_link("python", "notes")
        assert ".kos/graph.json" not in fs._files

    def test_explicit_save_works_when_auto_off(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, snapshot_path=".kos/graph.json")
        engine.set_auto_snapshot(False)
        engine.add_link("python", "notes")
        assert ".kos/graph.json" not in fs._files
        res = engine.save_graph()
        assert res["ok"] is True
        assert ".kos/graph.json" in fs._files

    def test_save_graph_without_fs_fails(self):
        engine = self._make_engine(fs=None, snapshot_path=None)
        res = engine.save_graph()
        assert res["ok"] is False
        assert "filesystem or snapshot path not configured" in res["error"]

    def test_agent_save_intent(self):
        r = ToolRegistry()
        r.register("save_graph", lambda: {"ok": True, "path": ".kos/graph.json"})
        r.register("auto_save", lambda enabled: {"ok": True, "enabled": enabled})
        svc = AgentService(r)
        assert svc.execute("save graph")["tool"] == "save_graph"
        assert svc.execute("auto save on")["tool"] == "auto_save"
        assert svc.execute("сохранить граф")["tool"] == "save_graph"
        assert svc.execute("автосохранение выкл")["tool"] == "auto_save"

    def test_repeat_add_link_does_not_write_twice(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, snapshot_path=".kos/graph.json")
        engine.add_link("python", "notes")
        first = fs._files[".kos/graph.json"]
        engine.add_link("python", "notes")
        second = fs._files[".kos/graph.json"]
        assert first == second

    def test_auto_snapshot_status_reflects_deps(self):
        fs = MockFS()
        engine = self._make_engine(fs=fs, snapshot_path=".kos/graph.json")
        status = engine.auto_snapshot_status()
        assert status["configured"] is True
        assert status["enabled"] is True
        assert status["path"] == ".kos/graph.json"

    def test_snapshot_failure_does_not_rollback_mutation(self):
        class FailingFS:
            def write_content(self, path, data):
                raise OSError("disk full")
            def read_content(self, path):
                return None
            def rename(self, old, new):
                pass

        b = InMemoryGraphBuilder()
        b.add_node("python.md", "Python", {})
        b.add_node("notes.md", "Notes", {})
        engine = GraphQueryEngine(b, fs=FailingFS(), snapshot_path=".kos/graph.json")
        res = engine.add_link("python", "notes")
        assert res["ok"] is True
        assert res["created"] is True
        edges = engine._snapshot()["edges"]
        assert any(e["from"] == "python.md" and e["to"] == "notes.md" for e in edges)
