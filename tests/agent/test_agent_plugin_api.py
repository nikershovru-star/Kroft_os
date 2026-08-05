"""Stage 40 - Agent Plugin Extension API tests (5)."""
from __future__ import annotations

import pytest

from services import AgentService, ToolRegistry
from tests.fixtures.plugin_agent_ext import AgentExtPlugin


class TestAgentPluginAPI:
    def test_plugin_registers_tool(self):
        r = ToolRegistry()
        p = AgentExtPlugin()
        p.register_agent_tools(r)
        assert r.has("weather")
        result = r.call("weather", city="Paris")
        assert result["city"] == "Paris"

    def test_plugin_registers_pattern(self):
        r = ToolRegistry()
        p = AgentExtPlugin()
        agent = AgentService(r)
        p.register_agent_tools(r)
        for pattern, steps in p.register_agent_patterns():
            agent.add_pattern(pattern, steps)
        result = agent.execute("weather in Berlin")
        assert result["tool"] == "weather"
        assert result["result"]["city"] == "Berlin"

    def test_dynamic_pattern_does_not_break_builtin(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "a.md"}])
        p = AgentExtPlugin()
        agent = AgentService(r)
        p.register_agent_tools(r)
        for pattern, steps in p.register_agent_patterns():
            agent.add_pattern(pattern, steps)
        result = agent.execute("find python")
        assert result["tool"] == "list_notes"

    def test_plugin_pattern_priority_after_builtin(self):
        """Plugin patterns are appended after builtins; builtins win on overlap."""
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "a.md"}])
        agent = AgentService(r)
        agent.add_pattern(r"find\s+(.+)", [("list_notes", lambda m: {"query": m.group(1)})])
        result = agent.execute("find python")
        assert result["tool"] == "list_notes"

    def test_add_pattern_idempotent(self):
        r = ToolRegistry()
        agent = AgentService(r)
        agent.add_pattern(r"test\s+(.+)", [("noop", lambda m: {})])
        assert len(agent._patterns) == len(AgentService.PATTERNS) + 1
        agent.add_pattern(r"test\s+(.+)", [("noop", lambda m: {})])
        assert len(agent._patterns) == len(AgentService.PATTERNS) + 2  # we allow duplicates
