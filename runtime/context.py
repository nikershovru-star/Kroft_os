"""Runtime Context — mutable state object shared across the kernel.

Holds the capability registry and any cross-cutting runtime state.
Services receive this context in their initialize() hook.
"""
from __future__ import annotations
from typing import Any, Dict

from contracts import ICapabilityRegistry
from .capability_registry import CapabilityRegistry


class RuntimeContext:
    def __init__(self) -> None:
        self.capabilities: ICapabilityRegistry = CapabilityRegistry()
        self.state: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    @property
    def capability_names(self) -> list[str]:
        return self.capabilities.names()
