"""ConfigService — centralized config READ (no apply; LAW K5 defers to ConfigApplier).

Per Phase 3: platforms receive parameters through this port, not by reading files
directly — breaks the hard FS coupling. Reads via stdlib (json/pathlib) only;
depends on contracts (IEventBus) + stdlib (arch-gate LAW K8). Never applies config:
applying is a two-phase commit (Wave 13 ConfigApplier.propose() -> approve()).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from contracts import IEventBus


class ConfigService:
    """Loads config.json / ENV once; serves values via get(); reloadable without restart."""

    def __init__(
        self,
        bus: IEventBus,
        config_path: Optional[Path] = None,
        logger: Any = None,
    ) -> None:
        self._bus = bus
        self._config_path = Path(config_path) if config_path else (Path.cwd() / "config.json")
        self._log = logger
        self._data: Dict[str, Any] = {}
        self.reload()
        bus.subscribe("config.request", self._on_request)

    def reload(self) -> Dict[str, Any]:
        """Re-read config from disk (no restart required)."""
        if self._config_path.exists():
            try:
                import json
                self._data = json.loads(self._config_path.read_text(encoding="utf-8"))
            except Exception as exc:
                if self._log:
                    self._log.warn("config.reload.failed", error=str(exc))
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def _on_request(self, event: dict) -> None:
        # Observability only: republish current config snapshot. Does NOT apply.
        self._bus.publish_sync("config.snapshot", {"config": self.as_dict()})
        if self._log:
            self._log.info("config.request", keys=list(self._data.keys()))
