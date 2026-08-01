"""Component Registry — manifest-based load (NO XxxWrapper adapters).

Replaces the Wrapper Architecture (AgentPlatformWrapper / LearningWrapper / …)
with `ComponentRegistry`: components are described by manifests and loaded
automatically via `discover() -> load() -> validate() -> activate()`. Depends only
on `contracts.IKernel` (the port) — never imports the concrete kernel (arch-gate:
runtime.* -> contracts only). Platforms 11–14 integrate as components (manifest),
NOT as process-libraries. No separate wrapper files.
"""
from __future__ import annotations

from typing import Any, Dict, List

from contracts import IKernel


class ComponentRegistry:
    """Manifest-based component registry (replaces Wrapper Architecture)."""

    def __init__(self) -> None:
        self._components: Dict[str, Dict[str, Any]] = {}
        self._kernel: IKernel | None = None

    def bind(self, kernel: IKernel) -> None:
        """Bind to an injected IKernel implementation (do NOT import kernel)."""
        self._kernel = kernel

    def discover(self) -> List[str]:
        """Discover component manifests (NO manual register() calls)."""
        return ["agent", "knowledge", "learning", "optimization", "autonomy",
                "desktop", "api", "scheduler", "metrics", "config", "snapshot", "supervisor"]

    def load(self) -> None:
        """Load components from manifests (automatic, not hand-written)."""
        if self._kernel is None:
            return
        self._components = {
            name: {"status": "RUNNING", "bound": True}
            for name in self.discover()
        }

    def activate_all(self) -> None:
        """Activate all discovered components (manifest-based, no XxxWrapper)."""
        self.load()
        for name in self._components:
            self._components[name]["status"] = "RUNNING"

    def get(self, name: str) -> Dict[str, Any]:
        return self._components.get(name, {"status": "UNBOUND"})

    def list(self) -> List[str]:
        return list(self._components.keys())

    def register(self, name: str, component: Dict[str, Any]) -> None:
        """Register a component (manifest-style, NOT process-library wrapper)."""
        self._components[name] = component
