"""Capability registry port.

The runtime context exposes capabilities (services/abilities) through a
registry so consumers resolve them by name without hard coupling.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class ICapabilityRegistry(ABC):
    """Contract for registering and resolving capabilities."""

    @abstractmethod
    def register(self, name: str, capability: Any) -> None: ...

    @abstractmethod
    def resolve(self, name: str) -> Any: ...

    @abstractmethod
    def has(self, name: str) -> bool: ...

    @abstractmethod
    def names(self) -> "list[str]": ...
