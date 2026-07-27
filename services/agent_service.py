"""AgentService — rule-based intent router (Stage 33)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .tool_registry import ToolRegistry


class AgentService:
    """Rule-based agent: matches natural language to registered tools."""

    # (regex_pattern, tool_name, extract_fn) -- extract_fn returns kwargs dict
    PATTERNS: List[Tuple[str, str, Any]] = [
        (r"find\s+(.+?)\s+and\s+open\s+(?:the\s+)?best", "open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1}),
        (r"find\s+(.+?)(?:\s+and\s+open)?$", "list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5}),
        (r"open\s+(.+)$", "open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1}),
        (r"show\s+(?:me\s+)?(.+)$", "list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5}),
        (r"what\s+is\s+(?:the\s+)?most\s+central", "most_central", lambda m: {}),
        (r"export\s+(?:graph|vault)\s+to\s+(\w+)", "export_graph", lambda m: {"fmt": m.group(1)}),
        (r"take\s+a\s+screenshot", "screenshot", lambda m: {}),
        (r"cursor\s+position", "cursor_position", lambda m: {}),
        (r"centrality", "most_central", lambda m: {}),
        (r"orphan", "list_orphans", lambda m: {}),
    ]

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, command: str) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"error": "empty command"}
        cmd = command.strip().lower()
        for pattern, tool_name, extract in self.PATTERNS:
            m = re.search(pattern, cmd)
            if m:
                if not self._registry.has(tool_name):
                    return {"error": f"tool '{tool_name}' not available", "command": command}
                kwargs = extract(m)
                try:
                    result = self._registry.call(tool_name, **kwargs)
                    return {"ok": True, "command": command, "tool": tool_name, "result": result}
                except Exception as e:  # noqa: BLE001 -- surface tool errors to caller
                    return {"error": str(e), "command": command, "tool": tool_name}
        return {"error": "unknown command", "command": command, "hint": "try: find X, open X, show X, most central, export graph to dot, screenshot"}

    def plan(self, command: str) -> List[str]:
        """Return the execution plan without running (for dry-run)."""
        if not command or not command.strip():
            return []
        cmd = command.strip().lower()
        for pattern, tool_name, _ in self.PATTERNS:
            if re.search(pattern, cmd):
                return [f"match pattern -> call '{tool_name}'"]
        return ["no matching pattern found"]
