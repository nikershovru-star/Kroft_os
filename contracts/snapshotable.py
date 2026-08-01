"""Snapshotable port (Stage 19).

A `snapshot() -> dict` / `restore(data) -> None` contract for any service
whose in-memory state must survive a kernel restart without re-reading the
source of truth (the vault). `ContentIndex` is the first implementor: it
hands back a plain-dict and lets the Kernel + SnapshotStore write it to disk,
so the service itself never touches the file system.

`runtime_checkable` lets the Kernel decide "does this resolved service
implement ISnapshotable?" without importing the concrete class.
"""
from __future__ import annotations
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class ISnapshotable(Protocol):
    """An object whose state can be serialized to a plain-dict and rebuilt."""

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable plain-dict snapshot of the state."""
        ...

    def restore(self, data: Dict[str, Any]) -> None:
        """Replace the current state wholesale from a previously saved dict."""
        ...
