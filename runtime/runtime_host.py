"""Runtime Host — Component Registry based load (replaces Wrapper Architecture).

`RuntimeHost` orchestrates `discover() -> load() -> validate() -> activate()`
over the EXISTING microkernel (kernel/kernel.py). Does NOT create XxxWrapper
adapters; components are loaded by manifest, not by hand-written register() calls.
"""
from __future__ import annotations

from .component_registry import ComponentRegistry


class RuntimeHost:
    """Runtime Host — manifest-based component loading (no separate wrappers)."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def discover(self) -> list:
        """Discover components (manifest-based, NO XxxWrapper)."""
        return self.registry.discover()

    def load(self) -> None:
        """Load components from manifests (automatic)."""
        self.registry.load()

    def validate(self) -> bool:
        """Validate loaded components (manifest schema)."""
        return len(self.registry.list()) > 0

    def activate(self) -> None:
        """Activate all (manifest-based, not wrapper-style)."""
        self.registry.activate_all()
