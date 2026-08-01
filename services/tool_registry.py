"""ToolRegistry — register and invoke tools (Stage 33)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from contracts import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, name: str, fn: Callable[..., Any], description: str = "") -> None:
        self._tools[name] = Tool(name, fn, description)

    def call(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not registered")
        return self._tools[tool_name].fn(**kwargs)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def has(self, name: str) -> bool:
        return name in self._tools
