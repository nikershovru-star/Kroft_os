"""Core service port (Hexagonal Architecture).

Every domain capability in KROFT_OS is expressed as an IService.
Adapters and concrete implementations depend on this abstraction, never
the other way around.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class IService(ABC):
    """Base contract for all service components."""

    @abstractmethod
    def name(self) -> str:
        """Unique service identifier used by the runtime registry."""

    @abstractmethod
    def initialize(self, context: "Any | None" = None) -> None:
        """Lifecycle hook: acquire dependencies, prepare state."""

    @abstractmethod
    def execute(self, context_data: dict) -> "str | list[str]":
        """Execute the service unit of work and return a result."""
