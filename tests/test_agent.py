"""Stage 33 - Hermes Agent tests (8)."""
from __future__ import annotations

import json
import pytest

from services import AgentService, ToolRegistry


class TestAgentService:
    def _svc(self, tools=None):
        r = ToolRegistry()
        if tools:
            for name, fn in tools.items():
                r.register(name, fn)
        return AgentService(r)

    def test_empty_command(self):
        s = self._svc()
        assert s.execute("") == {"error": "empty command"}

    def test_unknown_command(self):
        s = self._svc()
        result = s.execute("fly to the moon")
        assert result["error"] == "unknown command"
        assert "hint" in result

    def test_find_and_list(self):
        s = self._svc({"list_notes": lambda query, top_k: [{"id": "a.md", "score": 0.9}]})
        result = s.execute("find python notes")
        assert result["ok"] is True
        assert result["tool"] == "list_notes"
        assert result["result"][0]["id"] == "a.md"

    def test_find_and_open(self):
        s = self._svc({"open_note": lambda query, top_k: {"ok": True, "opened": "a.md"}})
        result = s.execute("find python notes and open the best")
        assert result["ok"] is True
        assert result["tool"] == "open_note"

    def test_open_direct(self):
        s = self._svc({"open_note": lambda query, top_k: {"ok": True, "opened": "b.md"}})
        result = s.execute("open my note")
        assert result["ok"] is True

    def test_most_central(self):
        s = self._svc({"most_central": lambda: {"a.md": 3}})
        result = s.execute("what is the most central note")
        assert result["ok"] is True
        assert result["tool"] == "most_central"

    def test_screenshot(self):
        s = self._svc({"screenshot": lambda: {"size": 42}})
        result = s.execute("take a screenshot")
        assert result["ok"] is True
        assert result["result"]["size"] == 42

    def test_dry_run(self):
        s = self._svc({"list_notes": lambda **kw: []})
        plan = s.plan("find python")
        assert plan == ["match pattern -> call 'list_notes'"]
