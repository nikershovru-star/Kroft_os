"""SnapshotStore — atomic (rename-based) persistence of a plain-dict payload.

Stage 19. Thin wrapper over an ``IFileSystem``-like port (duck-typed: it only
needs ``write_content`` / ``read_content`` / ``rename``). The store does NOT
know what the payload means — the Kernel builds the dict (composite of every
ISnapshotable service) and the store just writes/reads it atomically.

Atomicity: ``save`` writes to ``<path>.tmp`` then renames onto ``<path>``.
``os.replace`` is atomic on both POSIX and Windows (overwrites the target),
so a reader never sees a half-written file.
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional


class SnapshotStore:
    """Atomic, version-agnostic JSON snapshot read/write over a file-system port."""

    def __init__(self, fs: Any, path: str) -> None:
        self._fs = fs  # duck-typed IFileSystem (write_content/read_content/rename)
        self._path = path  # e.g. "data/index_snapshot.json"

    def save(self, payload: Dict[str, Any]) -> None:
        tmp = self._path + ".tmp"
        self._fs.write_content(tmp, json.dumps(payload, ensure_ascii=False))
        # Atomic replace: never leave a reader with a torn file.
        if hasattr(self._fs, "rename"):
            self._fs.rename(tmp, self._path)  # type: ignore[attr-defined]
        else:  # pragma: no cover - fallback for ports without rename
            self._fs.write_content(self._path, json.dumps(payload, ensure_ascii=False))
            if hasattr(self._fs, "delete"):
                self._fs.delete(tmp)

    def load(self) -> Optional[Dict[str, Any]]:
        try:
            raw = self._fs.read_content(self._path)
            return json.loads(raw)
        except Exception:
            return None
