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
        # Stage 37: open_app must precede bare 'open' (else 'open_app x' is
        # swallowed by the open_note pattern).
        (
            r"open_app\s+(.+)$",
            [("desktop_open_app", lambda m: {"name": m.group(1).strip()})],
        ),
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
            [("show_note", lambda m: {"query": m.group(1).strip(), "top_k": 1})],
        ),
        (
            r"what\s+is\s+(?:the\s+)?most\s+central",
            [("most_central", lambda m: {})],
        ),
        (
            r"export\s+(?:graph|vault)\s+to\s+(\w+)",
            [("export_graph", lambda m: {"fmt": m.group(1)})],
        ),
        # Stage 37: export <fmt> [query] (spec v5.0, without 'graph to')
        (
            r"export\s+(dot|json|gexf)\b(?:\s+(.+))?$",
            [("export_format", lambda m: {"fmt": m.group(1)})],
        ),
        (
            r"take\s+a\s+screenshot",
            [("screenshot", lambda m: {})],
        ),
        (
            r"cursor\s+position",
            [("cursor_position", lambda m: {})],
        ),
        # Stage 37: NL desktop intents (spec v5.0)
        (
            r"click\s+(\d+)\s+(\d+)$",
            [("desktop_click", lambda m: {"x": m.group(1), "y": m.group(2)})],
        ),
        (
            r"type\s+(.+)$",
            [("desktop_type", lambda m: {"text": m.group(1).strip()})],
        ),
        # Stage 37: capabilities (spec v5.0: 'что ты умеешь')
        (
            r"what\s+can\s+you\s+do|что\s+ты\s+умеешь|что\s+ты\s+можешь",
            [("capabilities", lambda m: {})],
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
        # Stage 37: cyrillic NL desktop + show
        (
            r"клик\s+(\d+)\s+(\d+)$",
            [("desktop_click", lambda m: {"x": m.group(1), "y": m.group(2)})],
        ),
        (
            r"напечатай\s+(.+)$",
            [("desktop_type", lambda m: {"text": m.group(1).strip()})],
        ),
        (
            r"открой\s+приложение\s+(.+)$",
            [("desktop_open_app", lambda m: {"name": m.group(1).strip()})],
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
            [("show_note", lambda m: {"query": m.group(1).strip(), "top_k": 1})],
        ),
    ]

    def __init__(self, registry: ToolRegistry, session_store: Optional[Any] = None) -> None:
        self._registry = registry
        self._session = session_store
        self._local_find: List[Dict[str, Any]] = []  # fallback if no session_store

    def _get_last_find(self) -> List[Dict[str, Any]]:
        if self._session:
            return self._session.get_last_find()
        return self._local_find

    def _set_last_find(self, results: List[Dict[str, Any]], command: str = "") -> None:
        if self._session:
            self._session.set_last_find(results, command)
        else:
            self._local_find = results

    def _match(self, command: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return a plan (list of (tool_name, kwargs)) or []."""
        if not command or not command.strip():
            return []
        cmd = command.strip().lower()
        # Implicit reference: "open the first one" / "открой первую" -> last find top-1
        if re.fullmatch(r"(open|открой)\s+(the\s+)?(first|первую|первый)(\s+(one|result))?", cmd):
            if self._get_last_find():
                top = self._get_last_find()[0]
                return [("open_note", {"query": top.get("id", ""), "top_k": 1})]
            # No prior find in this/recovered session -> explicit error (stateless-safe)
            return [("__implicit_ref_no_context__", {})]
        if re.fullmatch(r"(show|покажи)\s+(the\s+)?(first|первую|первый)(\s+(one|result))?", cmd):
            if self._get_last_find():
                top = self._get_last_find()[0]
                return [("show_note", {"query": top.get("id", ""), "top_k": 1})]
            return [("__implicit_ref_no_context__", {})]
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
                "ok": False,
                "error": "unknown command",
                "command": command,
                "hint": "try: find X, open X, найди X, открой X, screenshot, сделай скриншот",
            }
        # Validate all tools exist before executing
        for tool_name, _ in plan:
            if not self._registry.has(tool_name):
                return {"ok": False, "error": f"tool '{tool_name}' not available", "command": command}
        # Execute sequentially (fail-fast: stop on first error)
        results: List[Dict[str, Any]] = []
        for tool_name, kwargs in plan:
            try:
                result = self._registry.call(tool_name, **kwargs)
                results.append({"tool": tool_name, "result": result})
            except Exception as e:  # noqa: BLE001 -- surface step errors, stop chain
                results.append({"tool": tool_name, "error": str(e)})
                break
        # SessionStore: remember find/list results for implicit "open the first"
        for step_result in results:
            if step_result.get("tool") == "list_notes" and "result" in step_result:
                self._set_last_find(step_result["result"], command)
        # Backward compat: single-step returns the old flat format (Stage 33),
        # enriched with spec v5.0 fields (action/query/results) where applicable.
        if len(results) == 1 and "error" not in results[0]:
            out = {
                "ok": True,
                "command": command,
                "tool": results[0]["tool"],
                "result": results[0]["result"],
            }
            if results[0]["tool"] in ("list_notes", "show_note"):
                out["action"] = "find" if results[0]["tool"] == "list_notes" else "show"
                out["query"] = plan[0][1].get("query", "")
                out["results"] = results[0]["result"] if isinstance(results[0]["result"], list) else [results[0]["result"]]
            elif results[0]["tool"] == "open_note":
                out["action"] = "open"
                out["target"] = results[0]["result"].get("opened") if isinstance(results[0]["result"], dict) else None
                out["opened_by"] = "default_app"
            elif results[0]["tool"] == "export_format":
                out["action"] = "export"
                out["format"] = plan[0][1].get("fmt")
            elif results[0]["tool"] == "capabilities":
                out["action"] = "capabilities"
            elif results[0]["tool"] == "screenshot":
                out["action"] = "desktop"
            elif results[0]["tool"] == "cursor_position":
                out["action"] = "desktop"
            elif results[0]["tool"] in ("desktop_click", "desktop_type", "desktop_open_app"):
                out["action"] = "desktop"
            return out
        return {"ok": True, "command": command, "plan": results}

    def plan(self, command: str) -> List[str]:
        """Dry-run: return step descriptions without executing."""
        if not command or not command.strip():
            return []
        plan = self._match(command)
        if not plan:
            return ["no matching pattern found"]
        return [f"step {i+1}: {tool_name}" for i, (tool_name, _) in enumerate(plan)]
