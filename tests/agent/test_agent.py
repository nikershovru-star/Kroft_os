"""Stage 33/34 - Hermes Agent tests (16)."""
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
        # Stage 34: "find X and open the best" is now a 2-step plan.
        s = self._svc({
            "list_notes": lambda query, top_k: [{"id": "a.md", "score": 0.9}],
            "open_note": lambda query, top_k: {"ok": True, "opened": "a.md"},
        })
        result = s.execute("find python notes and open the best")
        assert result["ok"] is True
        assert "plan" in result
        assert len(result["plan"]) == 2
        assert result["plan"][0]["tool"] == "list_notes"
        assert result["plan"][1]["tool"] == "open_note"

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
        # Stage 34: plan() now returns ["step 1: list_notes"] style steps.
        s = self._svc({"list_notes": lambda **kw: []})
        plan = s.plan("find python")
        assert plan == ["step 1: list_notes"]


class TestMultiStepPlans:
    def test_find_and_open_best(self):
        """Two-step: list_notes then open_note."""
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k: [{"id": "a.md", "score": 0.9}])
        r.register("open_note", lambda query, top_k: {"ok": True, "opened": "a.md"})
        s = AgentService(r)
        result = s.execute("find python notes and open the best")
        assert result["ok"] is True
        assert "plan" in result
        assert len(result["plan"]) == 2
        assert result["plan"][0]["tool"] == "list_notes"
        assert result["plan"][1]["tool"] == "open_note"

    def test_find_and_screenshot(self):
        r = ToolRegistry()
        r.register("list_notes", lambda **kw: [])
        r.register("screenshot", lambda: {"size": 42})
        s = AgentService(r)
        result = s.execute("find python and take a screenshot")
        assert result["ok"] is True
        assert len(result["plan"]) == 2

    def test_open_and_screenshot(self):
        r = ToolRegistry()
        r.register("open_note", lambda **kw: {"ok": True})
        r.register("screenshot", lambda: {"size": 42})
        s = AgentService(r)
        result = s.execute("open my note and take a screenshot")
        assert result["ok"] is True
        assert len(result["plan"]) == 2

    def test_multi_step_error_stops_chain(self):
        """If step 2 fails, step 3 does not run (fail-fast)."""
        r = ToolRegistry()
        r.register("list_notes", lambda **kw: [])
        r.register("open_note", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        r.register("screenshot", lambda: {"size": 42})
        s = AgentService(r)
        # "find python and open the best" → step1 list_notes, step2 open_note (raises)
        result = s.execute("find python and open the best")
        assert result["ok"] is True
        assert len(result["plan"]) == 2  # only 2 steps, 3rd does not run
        assert "error" in result["plan"][1]
        assert result["plan"][1]["error"] == "boom"

    def test_plan_multi_step(self):
        r = ToolRegistry()
        s = AgentService(r)
        plan = s.plan("find python and open the best")
        assert plan == ["step 1: list_notes", "step 2: open_note"]


class TestCyrillic:
    def test_cyrillic_find(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k: [{"id": "py.md", "score": 0.9}])
        s = AgentService(r)
        result = s.execute("найди питон")
        assert result["ok"] is True
        assert result["tool"] == "list_notes"
        assert result["result"][0]["id"] == "py.md"

    def test_cyrillic_open(self):
        r = ToolRegistry()
        r.register("open_note", lambda query, top_k: {"ok": True, "opened": "b.md"})
        s = AgentService(r)
        result = s.execute("открой мою заметку")
        assert result["ok"] is True
        assert result["tool"] == "open_note"

    def test_cyrillic_screenshot(self):
        r = ToolRegistry()
        r.register("screenshot", lambda: {"size": 42})
        s = AgentService(r)
        result = s.execute("сделай скриншот")
        assert result["ok"] is True
        assert result["tool"] == "screenshot"

    def test_cyrillic_export_graph(self):
        r = ToolRegistry()
        r.register("export_graph", lambda fmt: {"format": fmt})
        s = AgentService(r)
        result = s.execute("экспортируй граф в dot")
        assert result["ok"] is True
        assert result["tool"] == "export_graph"
        assert result["result"]["format"] == "dot"
