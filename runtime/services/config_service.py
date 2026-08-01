"""ConfigService — centralized config READ + hot-reload (no apply; LAW K5).

Per Phase 3: platforms receive parameters through this port, not by reading files
directly. Reads via stdlib (json/pathlib) only; depends on contracts (IEventBus) +
stdlib (arch-gate LAW K8). Never applies config (apply is a two-phase commit via
Wave 13 ConfigApplier.propose() -> approve()).

Phase 5 (Hot Reload): `start_watching()` polls `config.json` via stdlib `os.stat`
(NO third-party watchdog — that would break the runtime arch-gate). On change it
reloads and publishes `config.changed`; it also republishes as a `kernel.lifecycle`
event (type=config.reloaded) so the Kernel sees hot-reload as an ordinary lifecycle
event (LAW K3 — the Kernel is NOT modified; it just observes the bus).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from contracts import IEventBus


class ConfigService:
    """Loads config.json / ENV; serves values via get(); reloadable without restart."""

    def __init__(
        self,
        bus: IEventBus,
        config_path: Optional[Path] = None,
        logger: Any = None,
        poll_interval: float = 1.0,
        sleep_fn: Callable[[float], None] = threading.Event().wait,
    ) -> None:
        self._bus = bus
        self._config_path = Path(config_path) if config_path else (Path.cwd() / "config.json")
        self._log = logger
        self._data: Dict[str, Any] = {}
        self._poll = poll_interval
        self._sleep = sleep_fn
        self._mtime: Optional[float] = None
        self._watching = False
        self._thread: Optional[threading.Thread] = None
        self.reload()
        bus.subscribe("config.request", self._on_request)

    def reload(self) -> Dict[str, Any]:
        """Re-read config from disk (no restart required)."""
        if self._config_path.exists():
            try:
                self._data = json.loads(self._config_path.read_text(encoding="utf-8"))
                self._mtime = os.stat(self._config_path).st_mtime
            except Exception as exc:
                if self._log:
                    self._log.warn("config.reload.failed", error=str(exc))
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    # --- Phase 5: hot reload ------------------------------------------------
    def _changed(self) -> bool:
        if not self._config_path.exists():
            return False
        try:
            mtime = os.stat(self._config_path).st_mtime
        except OSError:
            return False
        if self._mtime is None or mtime != self._mtime:
            self._mtime = mtime
            return True
        return False

    def start_watching(self) -> None:
        """Begin polling config.json for changes (stdlib os.stat only)."""
        if self._watching:
            return
        self._watching = True
        self._thread = threading.Thread(target=self._watch_loop, name="config-watch", daemon=True)
        self._thread.start()

    def stop_watching(self) -> None:
        self._watching = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _watch_loop(self) -> None:
        while self._watching:
            if self._changed():
                self.reload()
                self._bus.publish_sync("config.changed", {"config": self.as_dict()})
                # Kernel sees hot-reload as an ordinary lifecycle event (LAW K3).
                self._bus.publish_sync("kernel.lifecycle", {"type": "config.reloaded"})
                if self._log:
                    self._log.info("config.changed", keys=list(self._data.keys()))
            self._sleep(self._poll)

    def _on_request(self, event: dict) -> None:
        # Observability only: republish current config snapshot. Does NOT apply.
        self._bus.publish_sync("config.snapshot", {"config": self.as_dict()})
        if self._log:
            self._log.info("config.request", keys=list(self._data.keys()))
