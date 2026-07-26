"""KnowledgeOS v5 infrastructure — composition root."""
from .container import DependencyContainer
from .eventbus import InMemoryEventBus
from .graph_builder import InMemoryGraphBuilder

__all__ = ["DependencyContainer", "InMemoryEventBus", "InMemoryGraphBuilder"]
