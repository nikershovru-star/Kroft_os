"""Session Store — lightweight JSON persistence for agent context (Stage 39 + 41)."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


class SessionStore:
    """Thread-safe agent session with optional JSON disk backing."""

    def __init__(self, persistence_path: Optional[str] = None,
                 max_turns: int = 50) -> None:
        self._lock = threading.Lock()
        self._path = persistence_path
        self._max_turns = max_turns
        self._data: Dict[str, Any] = {
            "last_find": [],
            "last_command": "",
            "turns": [],  # Stage 41: conversation history
        }
        self.load()

    def set_last_find(self, results: List[Dict[str, Any]], command: str = "") -> None:
        with self._lock:
            self._data["last_find"] = results
            self._data["last_command"] = command
            self.save()

    def get_last_find(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("last_find", []))

    def add_turn(self, command: str, action: str, result_summary: str = "") -> None:
        with self._lock:
            self._data["turns"].append({
                "command": command,
                "action": action,
                "summary": result_summary,
                "ts": time.time(),
            })
            if len(self._data["turns"]) > self._max_turns:
                self._data["turns"] = self._data["turns"][-self._max_turns:]
            self.save()

    def get_turns(self, n: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            turns = list(self._data.get("turns", []))
            if n is not None:
                turns = turns[-n:]
            return turns

    def get_last_command(self) -> str:
        with self._lock:
            # Return the last NON-shortcut command: repeating a shortcut
            # (again/повтори/more/show) is meaningless and would recurse, so
            # walk back to the most recent real command.
            shortcuts = ("again", "повтори", "repeat", "more", "ещё", "еще", "show", "покажи")
            for turn in reversed(self._data.get("turns", [])):
                cmd = turn.get("command", "")
                if cmd and cmd not in shortcuts:
                    return cmd
            return ""

    def get_last_query(self) -> str:
        with self._lock:
            # heuristic: last command whose action was a find/list/show/open
            # (action stores the tool name: list_notes/show_note/open_note, but
            # also accepts the friendly names find/show/open for compatibility).
            for turn in reversed(self._data.get("turns", [])):
                if turn["action"] in ("find", "show", "open", "list_notes", "show_note", "open_note"):
                    return turn["command"]
            return ""

    def reset(self) -> None:
        with self._lock:
            self._data = {"last_find": [], "last_command": "", "turns": []}
            self.save()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def save(self) -> None:
        if not self._path:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            # Atomic write (ТЗ-L10.7): write to .tmp, fsync, atomic rename so a
            # crash never leaves a partially-written session file.
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        except Exception:
            pass

    def load(self) -> None:
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except json.JSONDecodeError:
            # Preserve corrupt session as .corrupt for diagnosis (no backup system).
            _corrupt = self._path + ".corrupt"
            try:
                if os.path.isfile(_corrupt):
                    os.remove(_corrupt)
                os.replace(self._path, _corrupt)
            except Exception:
                pass
        except Exception:
            pass
