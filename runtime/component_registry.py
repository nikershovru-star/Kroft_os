"""Component Registry — manifest-based load (NO XxxWrapper adapters).

Replaces the Wrapper Architecture (AgentPlatformWrapper / LearningWrapper / …)
with `ComponentRegistry`: components are described by manifests and loaded
automatically. Depends only on `contracts.IKernel` / `contracts.IProcess` (the
ports) — never imports the concrete kernel or platforms (arch-gate LAW K8).

Platforms 11–14 integrate as components (manifest), NOT as process-libraries.
No separate wrapper files. The composition root supplies real platform instances;
activate_platform wraps them as IProcess by duck-typing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import IKernel, IProcess, ProcessStatus

from runtime.manifest_schema import Manifest
from runtime.i_process_impl import Process
from runtime.plugin_loader import discover, validate


class ComponentRegistry:
    """Manifest-based component registry (replaces Wrapper Architecture)."""

    def __init__(self, plugins_dir: Optional[Path] = None) -> None:
        self._components: Dict[str, Dict[str, Any]] = {}
        self._processes: Dict[str, IProcess] = {}
        self._kernel: IKernel | None = None
        self._plugins_dir = plugins_dir

    def bind(self, kernel: IKernel) -> None:
        """Bind to an injected IKernel implementation (do NOT import kernel)."""
        self._kernel = kernel

    # --- Phase 2: platform integration core ---------------------------------
    def load_manifests(self) -> List[Manifest]:
        """Discover + validate manifests from plugins/. Returns valid manifests."""
        if self._plugins_dir is None:
            return []
        manifests = discover(self._plugins_dir)
        errors = validate(manifests)
        if errors:
            raise ValueError("Manifest validation failed: " + "; ".join(errors))
        return manifests

    def activate_platform(
        self, name: str, manifest: Manifest, instance: Any = None
    ) -> IProcess:
        """Register a platform as an IProcess (duck-typed, no platform mutation).

        `instance` is supplied by the composition root (platforms need injected
        ports, so they cannot be built from a bare manifest). If None, the
        component is registered declaratively (status RUNNING on activate).
        """
        proc = Process(
            name=name,
            instance=instance,
            capabilities=manifest.capabilities,
            dependencies=manifest.dependencies,
        )
        self._processes[name] = proc
        self._components[name] = {"status": "RUNNING", "bound": instance is not None,
                                   "manifest": manifest.to_dict()}
        proc.start()
        return proc

    def get_process(self, name: str) -> Optional[IProcess]:
        return self._processes.get(name)

    # --- legacy discovery (non-manifest) retained for smoke parity -----------
    def discover(self) -> List[str]:
        return list(self._components.keys()) or [
            "agent", "knowledge", "learning", "optimization", "autonomy",
            "desktop", "api", "scheduler", "metrics", "config", "snapshot", "supervisor",
        ]

    def load(self) -> None:
        if self._kernel is None:
            return
        base = self.discover()
        self._components = {n: {"status": "RUNNING", "bound": False} for n in base}

    def activate_all(self) -> None:
        self.load()
        for name in self._components:
            self._components[name]["status"] = "RUNNING"

    def get(self, name: str) -> Dict[str, Any]:
        return self._components.get(name, {"status": "UNBOUND"})

    def list(self) -> List[str]:
        # Prefer process registry (real platform components) when populated.
        if self._processes:
            return list(self._processes.keys())
        return list(self._components.keys())

    def stop_all(self) -> None:
        for proc in self._processes.values():
            try:
                proc.stop()
            except Exception:
                pass
        for comp in self._components.values():
            comp["status"] = "STOPPED"

    def register(self, name: str, component: Dict[str, Any]) -> None:
        self._components[name] = component
