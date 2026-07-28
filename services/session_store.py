"""Session Store — lightweight JSON persistence for agent context (Stage 39)."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional


class SessionStore:
    """Thread-safe agent session with optional JSON disk backing."""

    def __init__(self, persistence_path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._path = persistence_path
        self._data: Dict[str, Any] = {"last_find": [], "last_command": ""}
        self.load()

    def set_last_find(self, results: List[Dict[str, Any]], command: str = "") -> None:
        with self._lock:
            self._data["last_find"] = results
            self._data["last_command"] = command
            self.save()

    def get_last_find(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("last_find", []))

    def reset(self) -> None:
        with self._lock:
            self._data = {"last_find": [], "last_command": ""}
            self.save()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def save(self) -> None:
        if not self._path:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self) -> None:
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            pass
