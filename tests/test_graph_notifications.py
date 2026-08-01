"""Stage 55 — Graph-Driven Notifications tests."""
from __future__ import annotations

import time

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path: str, data: str) -> None:
        self._files[path] = data


class TestGraphNotifications:
    def _make_engine(self) -> GraphQueryEngine:
        b = InMemoryGraphBuilder()
        for nid, title in (
            ("python.md", "Python"),
            ("rust.md", "Rust"),
            ("go.md", "Go"),
            ("orphan.md", "Orphan"),
        ):
            b.add_node(nid, title, {"tags": ["lang"] if nid != "orphan.md" else []})
        b.add_edge("python.md", "rust.md", "links")
        b.add_edge("rust.md", "go.md", "links")
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="g.json")

    def test_check_and_notify_finds_orphan(self) -> None:
        engine = self._make_engine()
        r = engine.check_and_notify()
        assert r["ok"] is True
        assert r["new_notifications"] >= 1
        types = {n["type"] for n in r["notifications"]}
        assert "health" in types
        assert any("orphan" in n["message"].lower() for n in r["notifications"])

    def test_list_notifications_filters_acknowledged(self) -> None:
        engine = self._make_engine()
        engine.check_and_notify()
        pending = engine.list_notifications(acknowledged=False)
        assert pending["ok"] is True
        assert pending["notifications"]
        nid = pending["notifications"][0]["id"]
        engine.acknowledge_notification(nid)
        pending2 = engine.list_notifications(acknowledged=False)
        assert all(n["id"] != nid for n in pending2["notifications"])

    def test_dismiss_all_clears_pending(self) -> None:
        engine = self._make_engine()
        engine.check_and_notify()
        assert engine.list_notifications(acknowledged=False)["notifications"]
        engine.dismiss_all_notifications()
        assert len(engine.list_notifications(acknowledged=False)["notifications"]) == 0

    def test_interest_trigger_after_session_query(self) -> None:
        engine = self._make_engine()
        engine.record_user_query("sess-55", "python info", ["python.md"], intent="search")
        r = engine.check_and_notify(session_id="sess-55")
        interest_notes = [n for n in r["notifications"] if n["type"] == "interest"]
        assert interest_notes
        assert any("rust.md" in n["message"] or "go.md" in n["message"] for n in interest_notes)

    def test_agent_intents(self) -> None:
        reg = ToolRegistry()
        reg.register("check_and_notify", lambda **kw: {"ok": True})
        reg.register("list_notifications", lambda **kw: {"ok": True})
        reg.register("acknowledge_notification", lambda **kw: {"ok": True})
        reg.register("dismiss_all_notifications", lambda **kw: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("check notifications")["tool"] == "check_and_notify"
        assert svc.execute("show my notifications")["tool"] == "list_notifications"
        assert svc.execute("acknowledge notification abc123")["tool"] == "acknowledge_notification"
        assert svc.execute("dismiss all notifications")["tool"] == "dismiss_all_notifications"
        assert svc.execute("проверь уведомления")["tool"] == "check_and_notify"
        assert svc.execute("покажи уведомления")["tool"] == "list_notifications"
        assert svc.execute("подтверди уведомление abc123")["tool"] == "acknowledge_notification"
        assert svc.execute("очисти все уведомления")["tool"] == "dismiss_all_notifications"
