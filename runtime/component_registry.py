"""Component Registry — manifest-based load (NO XxxWrapper adapters).

Replaces the Wrapper Architecture (AgentPlatformWrapper / LearningWrapper / …)
with `ComponentRegistry`: components are described by manifests and loaded
automatically. Depends only on `contracts.IKernel` / `contracts.IProcess` (the
ports) — never imports the concrete kernel or platforms (arch-gate LAW K8).

Platforms 11–14 integrate as components (manifest), NOT as process-libraries.
No separate wrapper files. The composition root supplies real platform instances;
activate_platform wraps them as IProcess by duck-typing.

Phase 4: lifecycle is modelled with ProcessState (REGISTERED -> STARTING -> RUNNING).
`reactivate(name, instance)` is the restart hook — but the registry NEVER builds an
instance itself (LAW K8). The `instance` is produced by the IComponentController
(concrete impl in the composition root, wiring InstanceBuilder), so the Supervisor
stays ignorant of how/where/which platform is built.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from contracts import IKernel, IProcess, ProcessState

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
        # InstanceBuilder: name + manifest -> rebuilt instance (set by composition root).
        self._instance_builder: Optional[Callable[[str, Manifest], Any]] = None

    def bind(self, kernel: IKernel) -> None:
        """Bind to an injected IKernel implementation (do NOT import kernel)."""
        self._kernel = kernel

    def set_instance_builder(self, builder: Callable[[str, Manifest], Any]) -> None:
        """Composition root injects the builder; registry never builds itself (LAW K8)."""
        self._instance_builder = builder

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
        ports, so they cannot be built from a bare manifest). The process starts
        in REGISTERED -> STARTING -> RUNNING.
        """
        proc = Process(
            name=name,
            instance=instance,
            capabilities=manifest.capabilities,
            dependencies=manifest.dependencies,
        )
        self._processes[name] = proc
        self._components[name] = {"status": "REGISTERED", "bound": instance is not None,
                                   "manifest": manifest.to_dict()}
        proc.start()  # REGISTERED -> STARTING -> RUNNING
        self._components[name]["status"] = proc.state.value
        return proc

    def get_process(self, name: str) -> Optional[IProcess]:
        return self._processes.get(name)

    def get_manifest(self, name: str) -> Optional[Manifest]:
        comp = self._components.get(name)
        if comp is None:
            return None
        data = comp.get("manifest")
        return Manifest.from_dict(data) if data else None

    def reactivate(self, name: str, instance: Any = None) -> bool:
        """Restart hook used by IComponentController (composition root).

        The registry does NOT build the instance — `instance` is provided by the
        controller (which used InstanceBuilder). If None, the existing instance is
        reused. Returns True if the component came back RUNNING.
        """
        proc = self._processes.get(name)
        if proc is None:
            return False
        if instance is not None:
            proc.bind_instance(instance)
        return proc.restart()  # RECOVERING -> RUNNING (or QUARANTINED -> False)

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

    def swap(self, name: str, instance: Any) -> bool:
        """Hot-swap a component's instance in place (Phase 5), no Kernel.stop().

        Replaces the underlying instance and drives the process back to RUNNING
        via the RECOVERING->RUNNING transition. The Kernel is NOT stopped — the
        component is swapped live. Returns True if it came back RUNNING.
        """
        proc = self._processes.get(name)
        if proc is None:
            return False
        proc.bind_instance(instance)
        return proc.restart()  # RECOVERING -> RUNNING (or QUARANTINED -> False)

    def reload_manifests(self) -> List[str]:
        """Re-read plugins/*/manifest.yaml and activate any NEW components (Phase 5).

        Existing components are left untouched (no restart). Returns the list of
        newly activated component names. Manifest changes to existing components are
        ignored (live swap is a separate, explicit action via swap()).
        """
        if self._plugins_dir is None:
            return []
        current = set(self._processes.keys())
        manifests = self.load_manifests()
        activated: List[str] = []
        for m in manifests:
            if m.name in current:
                continue  # already running; not restarted on reload
            instance = None
            if self._instance_builder is not None:
                try:
                    instance = self._instance_builder(m.name, m)
                except Exception:
                    instance = None
            self.activate_platform(m.name, m, instance=instance)
            activated.append(m.name)
        return activated

    def register(self, name: str, component: Dict[str, Any]) -> None:
        self._components[name] = component
