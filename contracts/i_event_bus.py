"""Event bus port.

Enables the event-driven / event-sourcing model. Services publish and
subscribe through this abstraction; the kernel wires a concrete bus.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable


class IEventBus(ABC):
    """Contract for publish/subscribe messaging."""

    @abstractmethod
    def publish(self, event_type: str, payload: Any) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
