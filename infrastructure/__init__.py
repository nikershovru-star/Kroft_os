"""KnowledgeOS v5 infrastructure — composition root."""
from .container import DependencyContainer
from .eventbus import InMemoryEventBus

__all__ = ["DependencyContainer", "InMemoryEventBus"]
