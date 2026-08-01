"""Stage 60 — Graph Scheduled Maintenance tests."""
from __future__ import annotations

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path, data) -> None:
        self._files[path] = data


class TestGraphMaintenance:
    def _make_engine(self):
        builder = InMemoryGraphBuilder()
        for nid, title in (
            ("python.md", "Python"),
            ("rust.md", "Rust"),
            ("go.md", "Go"),
            ("duplicate.md", "Go"),
            ("orphan.md", "Orphan"),
        ):
            builder.add_node(nid, title, {"tags": ["lang"] if nid not in {"orphan.md"} else []})
        builder.add_edge("python.md", "rust.md", "links")
        builder.add_edge("rust.md", "go.md", "links")
        builder.add_edge("duplicate.md", "go.md", "links")
        return GraphQueryEngine(builder, fs=MockFS(), snapshot_path="tmp-graph-maintenance.json")

    def test_run_maintenance_cycle_dry_run(self):
        engine = self._make_engine()
        result = engine.run_maintenance_cycle(dry_run=True, auto_cleanup_orphans=True, auto_apply_suggestions=1, notify=True)
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["steps"]["health"]["orphan_count"] == 1
        assert result["steps"]["cleanup"]["removed"] == 0
        assert result["mutations_occurred"] is False
        assert result["duration_ms"] >= 0

    def test_run_maintenance_cycle_real_cleanup(self):
        engine = self._make_engine()
        result = engine.run_maintenance_cycle(dry_run=False, auto_cleanup_orphans=True, auto_apply_suggestions=0)
        assert result["ok"] is True
        assert result["steps"]["cleanup"]["removed"] == 1
        assert result["steps"]["cleanup"]["skipped"] is False
        assert "orphan.md" not in {node["id"] for node in engine._graph.get_graph()["nodes"]}
        assert result["mutations_occurred"] is True
        assert result["steps"]["snapshot"]["triggered"] is True
        assert engine.get_maintenance_history(limit=5)["history"]

    def test_run_maintenance_cycle_applies_suggestions(self):
        engine = self._make_engine()
        result = engine.run_maintenance_cycle(dry_run=False, auto_cleanup_orphans=True, auto_apply_suggestions=1, notify=False)
        assert result["ok"] is True
        assert result["steps"]["suggestions"]["scanned"] >= 1
        assert result["mutations_occurred"] is True
        edges = [(edge.get("from"), edge.get("to"), edge.get("relation")) for edge in engine._graph.get_graph()["edges"]]
        assert any(edge[0] == "duplicate.md" for edge in edges)

    def test_maintenance_history_logged(self):
        engine = self._make_engine()
        engine.run_maintenance_cycle(dry_run=True, notify=False)
        engine.run_maintenance_cycle(dry_run=False, auto_cleanup_orphans=True, auto_apply_suggestions=0, notify=False)
        history = engine.get_maintenance_history(limit=5)
        assert history["ok"] is True
        assert len(history["history"]) == 2
        assert history["history"][0]["dry_run"] is False
        assert history["history"][0]["steps"]["health"]["orphan_count"] == 1
        assert history["history"][1]["dry_run"] is True
        assert history["history"][1]["mutations"] is False

    def test_agent_intents(self):
        registry = ToolRegistry()
        registry.register("run_maintenance_cycle", lambda **kw: {"ok": True, "tool": "run_maintenance_cycle"})
        registry.register("get_maintenance_history", lambda **kw: {"ok": True, "tool": "get_maintenance_history"})
        registry.register("configure_maintenance", lambda **kw: {"ok": True, "tool": "configure_maintenance"})
        service = AgentService(registry)
        assert service.execute("run maintenance cycle")["tool"] == "run_maintenance_cycle"
        assert service.execute("preview maintenance")["tool"] == "run_maintenance_cycle"
        assert service.execute("maintenance history")["tool"] == "get_maintenance_history"
        assert service.execute("configure maintenance")["tool"] == "configure_maintenance"
        assert service.execute("запусти обслуживание графа")["tool"] == "run_maintenance_cycle"
        assert service.execute("предпросмотр обслуживания")["tool"] == "run_maintenance_cycle"
        assert service.execute("история обслуживания")["tool"] == "get_maintenance_history"
        assert service.execute("настрой обслуживание")["tool"] == "configure_maintenance"
