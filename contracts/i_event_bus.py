"""Event bus port.

Decouples publishers from subscribers. The kernel emits lifecycle events
through this abstraction; concrete async/in-memory buses implement it.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional


class IEventBus(ABC):
    """Contract for publish/subscribe messaging."""

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable) -> None: ...

    @abstractmethod
    def publish(self, topic: str, event: dict) -> None: ...

    @abstractmethod
    def publish_sync(self, topic: str, event: dict) -> None: ...

    @abstractmethod
    def get_history(self, topic: Optional[str] = None) -> List[dict]: ...

    @abstractmethod
    def clear_history(self) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
