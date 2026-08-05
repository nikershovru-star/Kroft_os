"""Stage 37 - Agent spec v5.0 alignment tests."""
from __future__ import annotations

import pytest

from services import AgentService, ToolRegistry


def _svc(tools=None):
    r = ToolRegistry()
    if tools:
        for name, fn in tools.items():
            r.register(name, fn)
    return AgentService(r)


class TestSpecShow:
    def test_show_maps_to_show_note(self):
        s = _svc({"show_note": lambda query, top_k=1: {"ok": True, "id": "a.md", "content": "# A"}})
        r = s.execute("show python tips")
        assert r["ok"] is True
        assert r["tool"] == "show_note"
        assert r["action"] == "show"
        assert r["query"] == "python tips"
        assert r["results"][0]["id"] == "a.md"

    def test_cyrillic_pokazhi_maps_to_show_note(self):
        s = _svc({"show_note": lambda query, top_k=1: {"ok": True, "id": "b.md", "content": "# B"}})
        r = s.execute("покажи заметку про бюджет")
        assert r["tool"] == "show_note"
        assert r["action"] == "show"
        assert r["query"] == "заметку про бюджет"


class TestSpecExportFormat:
    def test_export_format_without_graph_to(self):
        s = _svc({"export_format": lambda fmt: {"dot": "digraph{}"}})
        r = s.execute("export dot")
        assert r["ok"] is True
        assert r["tool"] == "export_format"
        assert r["action"] == "export"
        assert r["format"] == "dot"

    def test_export_json_still_works(self):
        s = _svc({"export_format": lambda fmt: {"nodes": []}})
        r = s.execute("export json")
        assert r["format"] == "json"


class TestSpecDesktopNL:
    def test_click_pattern(self):
        called = {}
        s = _svc({"desktop_click": lambda x, y: called.update(x=x, y=y) or {"ok": True}})
        r = s.execute("click 10 20")
        assert called == {"x": "10", "y": "20"}
        assert r["action"] is None or "tool" in r

    def test_type_pattern(self):
        called = {}
        s = _svc({"desktop_type": lambda text: called.update(text=text) or {"ok": True}})
        r = s.execute("type hello world")
        assert called["text"] == "hello world"

    def test_open_app_pattern(self):
        called = {}
        s = _svc({"desktop_open_app": lambda name: called.update(name=name) or {"ok": True}})
        r = s.execute("open_app notepad")
        assert called["name"] == "notepad"

    def test_cyrillic_click(self):
        called = {}
        s = _svc({"desktop_click": lambda x, y: called.update(x=x, y=y) or {"ok": True}})
        r = s.execute("клик 5 7")
        assert called == {"x": "5", "y": "7"}


class TestSpecCapabilities:
    def test_capabilities(self):
        s = _svc({"capabilities": lambda: {"actions": ["find", "open"], "hint": "..."}})
        r = s.execute("что ты умеешь")
        assert r["ok"] is True
        assert r["tool"] == "capabilities"
        assert "actions" in r["result"]

    def test_what_can_you_do(self):
        s = _svc({"capabilities": lambda: {"actions": ["find"], "hint": "..."}})
        r = s.execute("what can you do")
        assert r["tool"] == "capabilities"


class TestImplicitRefs:
    def test_open_first_uses_last_find(self):
        s = _svc({
            "list_notes": lambda query, top_k: [{"id": "x.md", "score": 0.9}],
            "open_note": lambda query, top_k: {"ok": True, "opened": query},
        })
        s.execute("find python")
        r = s.execute("open the first one")
        assert r["ok"] is True
        assert r["tool"] == "open_note"
        # implicit ref resolved to the top-1 id from the prior find
        assert r["result"]["opened"] == "x.md"

    def test_cyrillic_open_first(self):
        s = _svc({
            "list_notes": lambda query, top_k: [{"id": "y.md", "score": 0.8}],
            "open_note": lambda query, top_k: {"ok": True, "opened": query},
        })
        s.execute("найди питон")
        r = s.execute("открой первую")
        assert r["result"]["opened"] == "y.md"
