"""Example Stage 40 plugin that extends the agent."""
from contracts.plugin import Plugin
from services.tool_registry import ToolRegistry


class AgentExtPlugin(Plugin):
    def register_agent_tools(self, registry: ToolRegistry) -> None:
        registry.register("weather", lambda city: {"temp": 22, "city": city}, "Mock weather lookup")

    def register_agent_patterns(self):
        return [
            (r"weather\s+in\s+(.+)", [("weather", lambda m: {"city": m.group(1).strip()})]),
        ]
