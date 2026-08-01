"""KROFT_OS v5 infrastructure — composition root."""
from .container import DependencyContainer
from .eventbus import InMemoryEventBus
from .graph_builder import InMemoryGraphBuilder
from .config_loader import ConfigLoader
from .snapshot_store import SnapshotStore
from .plugin_loader import PluginLoader

__all__ = [
    "DependencyContainer",
    "InMemoryEventBus",
    "InMemoryGraphBuilder",
    "ConfigLoader",
    "SnapshotStore",
    "PluginLoader",
]
