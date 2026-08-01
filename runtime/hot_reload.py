"""Hot Reload — file watcher + reload orchestration (Phase 5).

Per Phase 5: config changes -> system applies without full restart. The file
watcher is STDONLY (os.stat polling) — NO third-party `watchdog`, which would
break the runtime arch-gate (LAW K8: runtime.* imports only contracts + stdlib).

- `FileWatcher`: polls mtimes of watched paths; fires callbacks on change.
- `HotReloadService`: watches config.json (-> ConfigService.reload + config.changed)
  and plugins/ (-> ComponentRegistry.reload_manifests, activates new plugins live).

Hot Reload is a runtime event the Kernel observes via the bus as an ordinary
`kernel.lifecycle` event — the Kernel is NOT modified (LAW K3).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from contracts import IEventBus, IProcessRegistry


class FileWatcher:
    """Stdlib-only (os.stat) polling watcher for a set of paths/dirs."""

    def __init__(
        self,
        poll_interval: float = 1.0,
        sleep_fn: Callable[[float], None] = None,
    ) -> None:
        self._poll = poll_interval
        self._sleep = sleep_fn or (lambda s: threading.Event().wait(s))
        self._targets: List[Path] = []
        self._mtimes: Dict[str, Optional[float]] = {}
        self._callbacks: List[Callable[[Path], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def watch(self, path: Path, on_change: Callable[[Path], None]) -> None:
        p = Path(path)
        self._targets.append(p)
        self._mtimes[str(p)] = self._mtime_of(p)
        self._callbacks.append(on_change)

    @staticmethod
    def _mtime_of(p: Path) -> Optional[float]:
        if p.is_dir():
            # dir change = newest mtime among manifest files
            newest: Optional[float] = None
            for f in p.rglob("*.yaml"):
                try:
                    m = os.stat(f).st_mtime
                    if newest is None or m > newest:
                        newest = m
                except OSError:
                    pass
            return newest
        try:
            return os.stat(p).st_mtime
        except OSError:
            return None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="file-watcher", daemon=True)
        self._thread.start()

    def poll_once(self) -> None:
        """Single poll iteration: fire callbacks for any target whose mtime changed."""
        for p, cb in zip(self._targets, self._callbacks):
            cur = self._mtime_of(p)
            prev = self._mtimes.get(str(p))
            if cur is not None and prev is not None and cur != prev:
                self._mtimes[str(p)] = cur
                cb(p)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while self._running:
            self.poll_once()
            self._sleep(self._poll)


class HotReloadService:
    """Orchestrates hot reload of config + manifests via FileWatcher."""

    def __init__(
        self,
        bus: IEventBus,
        config_service: Any,
        registry: IProcessRegistry,
        config_path: Optional[Path] = None,
        plugins_dir: Optional[Path] = None,
        logger: Any = None,
        poll_interval: float = 1.0,
        sleep_fn: Callable[[float], None] = None,
    ) -> None:
        self._bus = bus
        self._config = config_service
        self._registry = registry
        self._config_path = Path(config_path) if config_path else (Path.cwd() / "config.json")
        self._plugins_dir = Path(plugins_dir) if plugins_dir else (Path.cwd() / "plugins")
        self._log = logger
        self._watcher = FileWatcher(poll_interval=poll_interval, sleep_fn=sleep_fn)

    def start(self) -> None:
        self._watcher.watch(self._config_path, self._on_config_change)
        if self._plugins_dir.exists():
            self._watcher.watch(self._plugins_dir, self._on_plugins_change)
        self._watcher.start()

    def stop(self) -> None:
        self._watcher.stop()

    def _on_config_change(self, path: Path) -> None:
        if self._config is not None and hasattr(self._config, "reload"):
            self._config.reload()
        self._bus.publish_sync("config.changed", {"path": str(path)})
        self._bus.publish_sync("kernel.lifecycle", {"type": "config.reloaded"})
        if self._log:
            self._log.info("hotreload.config", path=str(path))

    def _on_plugins_change(self, path: Path) -> None:
        activated: List[str] = []
        if hasattr(self._registry, "reload_manifests"):
            activated = self._registry.reload_manifests()
        self._bus.publish_sync("manifest.reloaded", {"activated": activated})
        self._bus.publish_sync("kernel.lifecycle", {"type": "manifest.reloaded"})
        if self._log:
            self._log.info("hotreload.manifest", activated=activated)
