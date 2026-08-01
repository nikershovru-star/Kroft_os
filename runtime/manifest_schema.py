"""Manifest schema — declarative description of a runtime component.

Per Phase 2 (variant b): a Manifest describes a component (name, entrypoint,
capabilities, dependencies, lifecycle) but does NOT instantiate it. The composition
root builds the real instance and passes it to ComponentRegistry.activate_platform.
No wrapper files, no importlib-from-nothing instantiation (platforms need injected
ports, so they cannot be built from a bare manifest — LAW K3 + honest engineering).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Manifest:
    """Immutable component descriptor (YAML-loadable)."""

    name: str
    entrypoint: str                       # e.g. "services.agent_platform:AgentPlatform"
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    lifecycle: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Manifest":
        return cls(
            name=data["name"],
            entrypoint=data.get("entrypoint", ""),
            capabilities=list(data.get("capabilities", [])),
            dependencies=list(data.get("dependencies", [])),
            lifecycle=data.get("lifecycle", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entrypoint": self.entrypoint,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "lifecycle": self.lifecycle,
        }
