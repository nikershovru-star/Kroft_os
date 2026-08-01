"""Runtime Host — Component Registry orchestration (replaces Wrapper Architecture).

`RuntimeHost` orchestrates `discover() -> load() -> validate() -> activate()` over the
EXISTING microkernel (kernel/kernel.py, via IKernel port). Does NOT create XxxWrapper
adapters; components are loaded by manifest, not by hand-written register() calls.

Platform instances are supplied by the composition root via `instance_builder(name)`
(the composition root knows how to construct each platform with its injected ports).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from contracts import IKernel

from runtime.component_registry import ComponentRegistry
from runtime.manifest_schema import Manifest


class RuntimeHost:
    """Runtime Host — manifest-based component loading (no separate wrappers)."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def discover(self) -> List[Manifest]:
        return self.registry.load_manifests()

    def load(self) -> None:
        # Manifest discovery is the "load" step; activation happens in activate().
        self.discover()

    def validate(self) -> bool:
        try:
            manifests = self.discover()
        except ValueError:
            return False
        return len(manifests) > 0

    def activate(
        self,
        instance_builder: Optional[Callable[[str, Manifest], Any]] = None,
    ) -> Dict[str, Any]:
        """Activate all discovered manifests as IProcess components.

        `instance_builder(name, manifest)` returns the real platform instance
        (or None for declarative-only registration). Supplied by composition root.
        """
        manifests = self.discover()
        activated: Dict[str, Any] = {}
        for m in manifests:
            instance = None
            if instance_builder is not None:
                try:
                    instance = instance_builder(m.name, m)
                except Exception:
                    instance = None
            proc = self.registry.activate_platform(m.name, m, instance=instance)
            activated[m.name] = proc.status.value
        return activated
