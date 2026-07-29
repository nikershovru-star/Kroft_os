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
        # Stage 43: graph reasoning (English)
        (
            r"neighbors\s+of\s+(.+?)(?:\s+(in|out|both))?(?:\s+depth\s+(\d+))?$",
            [("graph_neighbors", lambda m: {
                "query": m.group(1).strip(),
                "direction": (m.group(2) or "both").lower(),
                "depth": int(m.group(3) or 1),
            })],
        ),
        (
            r"path\s+from\s+(.+?)\s+to\s+(.+)$",
            [("graph_path", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
            })],
        ),
        (
            r"cluster\s+around\s+(.+?)(?:\s+top\s+(\d+))?$",
            [("graph_cluster", lambda m: {
                "query": m.group(1).strip(),
                "k": int(m.group(2) or 5),
            })],
        ),
        # Stage 43: graph reasoning (Cyrillic)
        (
            r"соседи\s+(.+?)(?:\s+(вход|выход|оба))?(?:\s+глубина\s+(\d+))?$",
            [("graph_neighbors", lambda m: {
                "query": m.group(1).strip(),
                "direction": {"вход": "in", "выход": "out", "оба": "both"}.get(
                    (m.group(2) or "оба").lower(), "both"
                ),
                "depth": int(m.group(3) or 1),
            })],
        ),
        (
            r"путь\s+от\s+(.+?)\s+до\s+(.+)$",
            [("graph_path", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
            })],
        ),
        (
            r"кластер\s+вокруг\s+(.+?)(?:\s+топ\s+(\d+))?$",
            [("graph_cluster", lambda m: {
                "query": m.group(1).strip(),
                "k": int(m.group(2) or 5),
            })],
        ),
        # Stage 44: graph mutation (English)
        (
            r"link\s+(.+?)\s+to\s+(.+?)(?:\s+as\s+(.+))?$",
            [("graph_link", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
                "relation": (m.group(3) or "links").strip(),
            })],
        ),
        (
            r"unlink\s+(.+?)\s+from\s+(.+)$",
            [("graph_unlink", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
            })],
        ),
        (
            r"untag\s+(.+?)\s+(.+)$",
            [("graph_untag", lambda m: {
                "query": m.group(1).strip(),
                "tag": m.group(2).strip(),
            })],
        ),
        (
            r"tag\s+(.+?)\s+as\s+(.+)$",
            [("graph_tag", lambda m: {
                "query": m.group(1).strip(),
                "tag": m.group(2).strip(),
            })],
        ),
        # Stage 44: graph mutation (Russian)
        (
            r"связать\s+(.+?)\s+с\s+(.+?)(?:\s+как\s+(.+))?$",
            [("graph_link", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
                "relation": (m.group(3) or "links").strip(),
            })],
        ),
        (
            r"отвязать\s+(.+?)\s+от\s+(.+)$",
            [("graph_unlink", lambda m: {
                "from_query": m.group(1).strip(),
                "to_query": m.group(2).strip(),
            })],
        ),
        (
            r"убрать\s+тег\s+(.+?)\s+(.+)$",
            [("graph_untag", lambda m: {
                "query": m.group(1).strip(),
                "tag": m.group(2).strip(),
            })],
        ),
        (
            r"тег\s+(.+?)\s+(.+)$",
            [("graph_tag", lambda m: {
                "query": m.group(1).strip(),
                "tag": m.group(2).strip(),
            })],
        ),
        # Stage 45: graph link recommendations (English)
        (
            r"suggest\s+links\s+for\s+(.+?)(?:\s+top\s+(\d+))?$",
            [("graph_suggest", lambda m: {
                "query": m.group(1).strip(),
                "top_k": int(m.group(2) or 5),
            })],
        ),
        (
            r"what\s+should\s+link\s+to\s+(.+?)(?:\s+top\s+(\d+))?$",
            [("graph_suggest", lambda m: {
                "query": m.group(1).strip(),
                "top_k": int(m.group(2) or 5),
            })],
        ),
        # Stage 45: graph link recommendations (Russian)
        (
            r"предложи\s+связи\s+для\s+(.+?)(?:\s+топ\s+(\d+))?$",
            [("graph_suggest", lambda m: {
                "query": m.group(1).strip(),
                "top_k": int(m.group(2) or 5),
            })],
        ),
        (
            r"с\s+чем\s+связать\s+(.+?)(?:\s+топ\s+(\d+))?$",
            [("graph_suggest", lambda m: {
                "query": m.group(1).strip(),
                "top_k": int(m.group(2) or 5),
            })],
        ),
        # Stage 46: graph analytics & health (English)
        (
            r"graph\s+stats",
            [("graph_stats", lambda m: {})],
        ),
        (
            r"orphan\s+notes?",
            [("graph_orphans", lambda m: {})],
        ),
        (
            r"most\s+central(?:\s+top\s+(\d+))?",
            [("graph_central", lambda m: {"k": int(m.group(1) or 5)})],
        ),
        (
            r"graph\s+health",
            [("graph_health", lambda m: {})],
        ),
        # Stage 46: graph analytics & health (Russian)
        (
            r"статистика\s+графа",
            [("graph_stats", lambda m: {})],
        ),
        (
            r"осиротевшие\s+заметки",
            [("graph_orphans", lambda m: {})],
        ),
        (
            r"самые\s+центральные(?:\s+топ\s+(\d+))?",
            [("graph_central", lambda m: {"k": int(m.group(1) or 5)})],
        ),
        (
            r"здоровье\s+графа",
            [("graph_health", lambda m: {})],
        ),
        # Stage 47: graph snapshot persistence (English)
        (
            r"save\s+graph",
            [("save_graph", lambda m: {})],
        ),
        (
            r"auto\s+save\s+(on|off)",
            [("auto_save", lambda m: {"enabled": m.group(1).lower() == "on"})],
        ),
        # Stage 47: graph snapshot persistence (Russian)
        (
            r"сохранить\s+граф",
            [("save_graph", lambda m: {})],
        ),
        (
            r"автосохранение\s+(вкл|выкл)",
            [("auto_save", lambda m: {"enabled": m.group(1).lower() == "вкл"})],
        ),
        # Stage 48: graph-enhanced hybrid search
        (
            r"hybrid\s+search\s+(.+)$",
            [("enhanced_search", lambda m: {"query": m.group(1).strip()})],
        ),
        (
            r"гибридный\s+поиск\s+(.+)$",
            [("enhanced_search", lambda m: {"query": m.group(1).strip()})],
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
        # Stage 41: contextual shortcuts (conversation-aware)
        (
            r"^(again|повтори|repeat)$",
            [("__again__", lambda m: {})],
        ),
        (
            r"^(more|ещ[её]|еще)$",
            [("__more__", lambda m: {})],
        ),
        (
            r"^(show|покажи)$",
            [("__show_last__", lambda m: {})],
        ),
    ]

    def __init__(self, registry: ToolRegistry, session_store: Optional[Any] = None) -> None:
        self._registry = registry
        self._session = session_store
        self._local_find: List[Dict[str, Any]] = []  # fallback if no session_store
        self._patterns: List[Tuple[str, List[Tuple[str, Callable[[Any], Dict[str, Any]]]]]] = []
        self._patterns.extend(self.PATTERNS)  # copy class-level defaults

    def _get_last_find(self) -> List[Dict[str, Any]]:
        if self._session:
            return self._session.get_last_find()
        return self._local_find

    def _set_last_find(self, results: List[Dict[str, Any]], command: str = "") -> None:
        if self._session:
            self._session.set_last_find(results, command)
        else:
            self._local_find = results

    def add_pattern(self, pattern: str, steps: List[Tuple[str, Callable[[Any], Dict[str, Any]]]]) -> None:
        """Stage 40: register a dynamic NL pattern (plugin extension)."""
        self._patterns.append((pattern, steps))

    def _match(self, command: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return a plan (list of (tool_name, kwargs)) or []."""
        if not command or not command.strip():
            return []
        cmd = command.strip().lower()
        orig = command.strip()  # preserve argument casing for extract fns
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
        # Stage 41: contextual shortcuts resolved against session history
        if cmd in ("again", "повтори", "repeat"):
            last = self._session.get_last_command() if self._session else ""
            # Guard against repeat-shortcut recursion: "again" after "again"
            # would resolve to itself and loop forever. A shortcut cannot be
            # repeated; without a real prior command there is no context.
            if last and last not in ("again", "повтори", "repeat", "more", "ещё", "еще", "show", "покажи"):
                return self._match(last)  # re-resolve
            return [("__no_context__", {})]
        if cmd in ("more", "ещё", "еще"):
            last_q = self._session.get_last_query() if self._session else ""
            if last_q:
                return [("list_notes", {"query": last_q, "top_k": 10})]
            return [("__no_context__", {})]
        if cmd in ("show", "покажи"):
            last_find = self._get_last_find()
            if last_find:
                return [("show_note", {"query": last_find[0].get("id", ""), "top_k": 1})]
            return [("__no_context__", {})]
        for pattern, steps in self._patterns:
            m = re.search(pattern, cmd)
            if m:
                # Re-match on original case so extracted args keep their casing
                # (e.g. "weather in Berlin" -> city "Berlin", not "berlin").
                m_orig = re.search(pattern, orig)
                return [(tool_name, extract(m_orig)) for tool_name, extract in steps]
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
        # Stage 41: contextual shortcut with no conversation context
        if plan[0][0] == "__no_context__":
            return {
                "ok": False,
                "error": "no conversation context",
                "command": command,
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
            # Stage 41: conversation history
            summary = ""
            if results:
                first = results[0]
                if "error" in first:
                    summary = f"error: {first['error']}"
                elif first.get("tool") == "list_notes":
                    summary = f"found {len(first.get('result', []))} notes"
                elif first.get("tool") == "open_note":
                    summary = f"opened {first.get('result', {}).get('opened', '?')}"
                elif first.get("tool") == "show_note":
                    summary = f"showed {first.get('result', {}).get('id', '?')}"
                elif first.get("tool") == "export_format":
                    summary = f"exported {first.get('result', {}).get('format', '?')}"
                else:
                    summary = first.get("tool", "unknown")
            if self._session:
                self._session.add_turn(
                    command,
                    results[0].get("tool", "unknown") if results else "noop",
                    summary,
                )
            return out
        # Stage 41: conversation history (multi-step path)
        summary = ""
        if results:
            first = results[0]
            if "error" in first:
                summary = f"error: {first['error']}"
            elif first.get("tool") == "list_notes":
                summary = f"found {len(first.get('result', []))} notes"
            elif first.get("tool") == "open_note":
                summary = f"opened {first.get('result', {}).get('opened', '?')}"
            elif first.get("tool") == "show_note":
                summary = f"showed {first.get('result', {}).get('id', '?')}"
            elif first.get("tool") == "export_format":
                summary = f"exported {first.get('result', {}).get('format', '?')}"
            else:
                summary = first.get("tool", "unknown")
        if self._session:
            self._session.add_turn(
                command,
                results[0].get("tool", "unknown") if results else "noop",
                summary,
            )
        return {"ok": True, "command": command, "plan": results}

    def execute_batch(
        self,
        commands: List[str],
        continue_on_error: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a sequence of commands with shared session context."""
        results: List[Dict[str, Any]] = []
        for cmd in commands:
            result = self.execute(cmd)
            results.append(result)
            if not continue_on_error and not result.get("ok", True):
                break
        return results

    def plan(self, command: str) -> List[str]:
        """Dry-run: return step descriptions without executing."""
        if not command or not command.strip():
            return []
        plan = self._match(command)
        if not plan:
            return ["no matching pattern found"]
        return [f"step {i+1}: {tool_name}" for i, (tool_name, _) in enumerate(plan)]
