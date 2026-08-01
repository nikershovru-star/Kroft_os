"""SnapshotService — dumps ComponentRegistry / ProcessRegistry state to JSON.

Per Phase 3 (Observability Foundation): debug distributed state by dumping the
runtime registry on demand (via `snapshot.request` on the event bus). Depends ONLY
on contracts (IEventBus, IProcessRegistry) + stdlib (arch-gate LAW K8). Read-only:
never mutates platforms or the registry.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from contracts import IEventBus, IProcessRegistry, ProcessStatus


class SnapshotService:
    """Dumps registry state to snapshot_*.json when a snapshot.request event fires."""

    def __init__(
        self,
        bus: IEventBus,
        registry: IProcessRegistry,
        out_dir: Optional[Path] = None,
        logger: Any = None,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._out_dir = Path(out_dir) if out_dir else Path.cwd()
        self._log = logger
        bus.subscribe("snapshot.request", self._on_request)

    def dump(self) -> Path:
        """Write the current registry snapshot and return its path."""
        self._out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self._out_dir / f"snapshot_{ts}.json"
        procs = []
        for name in self._registry.list():
            proc = self._registry.get(name)
            procs.append({
                "name": name,
                "pid": getattr(proc, "pid", None),
                "status": getattr(proc, "state", ProcessStatus.UNBOUND).value
                if proc is not None else "UNBOUND",
            })
        payload = {"generated_at": ts, "processes": procs}
        try:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            if self._log:
                self._log.warn("snapshot.write.failed", error=str(exc))
        if self._log:
            self._log.info("snapshot.dumped", path=str(path), processes=len(procs))
        return path

    def _on_request(self, event: dict) -> None:
        path = self.dump()
        self._bus.publish_sync("snapshot.taken", {"path": str(path)})
