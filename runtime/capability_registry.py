"""Capability registry — concrete implementation of ICapabilityRegistry.

Resolved by name at runtime so consumers never hard-wire concrete
services. Lives inside the Runtime Context.
"""
from __future__ import annotations
from typing import Any, Dict

from contracts import ICapabilityRegistry


class CapabilityRegistry(ICapabilityRegistry):
    def __init__(self) -> None:
        self._caps: Dict[str, Any] = {}

    def register(self, name: str, capability: Any) -> None:
        if not name:
            raise ValueError("capability name must be non-empty")
        self._caps[name] = capability

    def resolve(self, name: str) -> Any:
        if name not in self._caps:
            raise KeyError(f"Capability '{name}' is not registered.")
        return self._caps[name]

    def has(self, name: str) -> bool:
        return name in self._caps

    def names(self) -> list[str]:
        return list(self._caps.keys())
