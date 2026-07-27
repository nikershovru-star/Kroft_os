"""AgentService — rule-based intent router with multi-step plans (Stage 34)."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Tuple

from .tool_registry import ToolRegistry


class AgentService:
    """Rule-based agent: matches natural language to multi-step tool plans."""

    # Each pattern: (regex, [(tool_name, extract_fn), ...])
    # extract_fn receives the match object and returns a kwargs dict.
    # PATTERNS order MATTERS: multi-step patterns must precede the matching
    # single-step ones so the more specific command is matched first.
    PATTERNS: List[Tuple[str, List[Tuple[str, Callable[[Any], Dict[str, Any]]]]]] = [
        # --- English multi-step ---
        (
            r"find\s+(.+?)\s+and\s+open\s+(?:the\s+)?best",
            [
                ("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5}),
                ("open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1}),
            ],
        ),
        (
            r"find\s+(.+?)\s+and\s+take\s+a\s+screenshot",
            [
                ("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5}),
                ("screenshot", lambda m: {}),
            ],
        ),
        (
            r"open\s+(.+?)\s+and\s+take\s+a\s+screenshot",
            [
                ("open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1}),
                ("screenshot", lambda m: {}),
            ],
        ),
        # --- English single-step (preserved from Stage 33) ---
        (
            r"find\s+(.+?)(?:\s+and\s+open)?$",
            [("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5})],
        ),
        (
            r"open\s+(.+)$",
            [("open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1})],
        ),
        (
            r"show\s+(?:me\s+)?(.+)$",
            [("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5})],
        ),
        (
            r"what\s+is\s+(?:the\s+)?most\s+central",
            [("most_central", lambda m: {})],
        ),
        (
            r"export\s+(?:graph|vault)\s+to\s+(\w+)",
            [("export_graph", lambda m: {"fmt": m.group(1)})],
        ),
        (
            r"take\s+a\s+screenshot",
            [("screenshot", lambda m: {})],
        ),
        (
            r"cursor\s+position",
            [("cursor_position", lambda m: {})],
        ),
        (
            r"centrality",
            [("most_central", lambda m: {})],
        ),
        (
            r"orphan",
            [("list_orphans", lambda m: {})],
        ),
        # --- Cyrillic single-step ---
        (
            r"найди\s+(.+)$",
            [("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5})],
        ),
        (
            r"открой\s+(.+)$",
            [("open_note", lambda m: {"query": m.group(1).strip(), "top_k": 1})],
        ),
        (
            r"сделай\s+скриншот",
            [("screenshot", lambda m: {})],
        ),
        (
            r"позиция\s+курсора",
            [("cursor_position", lambda m: {})],
        ),
        (
            r"экспортируй\s+граф\s+в\s+(\w+)",
            [("export_graph", lambda m: {"fmt": m.group(1)})],
        ),
        (
            r"центральность",
            [("most_central", lambda m: {})],
        ),
        (
            r"осиротевшие",
            [("list_orphans", lambda m: {})],
        ),
        (
            r"покажи\s+(.+)$",
            [("list_notes", lambda m: {"query": m.group(1).strip(), "top_k": 5})],
        ),
    ]

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def _match(self, command: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return a plan (list of (tool_name, kwargs)) or []."""
        if not command or not command.strip():
            return []
        cmd = command.strip().lower()
        for pattern, steps in self.PATTERNS:
            m = re.search(pattern, cmd)
            if m:
                return [(tool_name, extract(m)) for tool_name, extract in steps]
        return []

    def execute(self, command: str) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"error": "empty command"}
        plan = self._match(command)
        if not plan:
            return {
                "error": "unknown command",
                "command": command,
                "hint": "try: find X, open X, найди X, открой X, screenshot, сделай скриншот",
            }
        # Validate all tools exist before executing
        for tool_name, _ in plan:
            if not self._registry.has(tool_name):
                return {"error": f"tool '{tool_name}' not available", "command": command}
        # Execute sequentially (fail-fast: stop on first error)
        results: List[Dict[str, Any]] = []
        for tool_name, kwargs in plan:
            try:
                result = self._registry.call(tool_name, **kwargs)
                results.append({"tool": tool_name, "result": result})
            except Exception as e:  # noqa: BLE001 -- surface step errors, stop chain
                results.append({"tool": tool_name, "error": str(e)})
                break
        # Backward compat: single-step returns the old flat format (Stage 33).
        if len(results) == 1 and "error" not in results[0]:
            return {
                "ok": True,
                "command": command,
                "tool": results[0]["tool"],
                "result": results[0]["result"],
            }
        return {"ok": True, "command": command, "plan": results}

    def plan(self, command: str) -> List[str]:
        """Dry-run: return step descriptions without executing."""
        if not command or not command.strip():
            return []
        plan = self._match(command)
        if not plan:
            return ["no matching pattern found"]
        return [f"step {i+1}: {tool_name}" for i, (tool_name, _) in enumerate(plan)]
