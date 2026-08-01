"""StateRepository — реализация IStateRepository (ADR-029, Phase B.3).

Обёртка над SnapshotStore (атомарный JSON) + checkpoint/rollback через
отдельные файлы `<path>.checkpoint.<label>`. Ядро (kernel) зависит ТОЛЬКО от
порта IStateRepository — эта реализация инжектируется из composition root.
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional

from .snapshot_store import SnapshotStore


class StateRepository:
    """Atomic snapshot + logical state + checkpoint/rollback over a file-system port."""

    def __init__(self, fs: Any, base_path: str = "data/state.json") -> None:
        self._fs = fs  # duck-typed IFileSystem (write_content/read_content/rename/delete)
        self._base = base_path
        self._snapshot = SnapshotStore(fs, base_path)

    # ----- IStateRepository: snapshot (composite graph/index payload) -----
    def save_snapshot(self, payload: Dict[str, Any]) -> None:
        self._snapshot.save(payload)

    def load_snapshot(self) -> Optional[Dict[str, Any]]:
        return self._snapshot.load()

    # ----- IStateRepository: logical state (runtime context, registry) -----
    def save_state(self, state: Dict[str, Any]) -> None:
        tmp = self._base + ".state.tmp"
        self._fs.write_content(tmp, json.dumps(state, ensure_ascii=False))
        if hasattr(self._fs, "rename"):
            self._fs.rename(tmp, self._base + ".state")
        else:  # pragma: no cover - fallback
            self._fs.write_content(self._base + ".state", json.dumps(state, ensure_ascii=False))
            if hasattr(self._fs, "delete"):
                self._fs.delete(tmp)

    def load_state(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._fs.read_content(self._base + ".state"))
        except Exception:
            return None

    # ----- IStateRepository: checkpoint / rollback -----
    def checkpoint(self, label: str) -> None:
        snap = self.load_snapshot() or {}
        state = self.load_state() or {}
        payload = {"snapshot": snap, "state": state}
        tmp = self._base + f".ckpt.{label}.tmp"
        self._fs.write_content(tmp, json.dumps(payload, ensure_ascii=False))
        if hasattr(self._fs, "rename"):
            self._fs.rename(tmp, self._base + f".ckpt.{label}")
        else:  # pragma: no cover - fallback
            self._fs.write_content(self._base + f".ckpt.{label}", json.dumps(payload, ensure_ascii=False))
            if hasattr(self._fs, "delete"):
                self._fs.delete(tmp)

    def rollback(self, label: str) -> bool:
        try:
            raw = self._fs.read_content(self._base + f".ckpt.{label}")
            payload = json.loads(raw)
        except Exception:
            return False
        if "snapshot" in payload:
            self.save_snapshot(payload["snapshot"])
        if "state" in payload:
            self.save_state(payload["state"])
        return True
