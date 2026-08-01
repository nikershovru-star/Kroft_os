"""composition/plugin_factory.py — Plugin assembly (Phase B.1)."""
from __future__ import annotations

from infrastructure import PluginLoader


def build_plugin_loader(plugin_dir: str):
    """Load a PluginLoader from a directory (or None)."""
    if plugin_dir is None:
        return None
    loader = PluginLoader(plugin_dir)
    loader.load()
    return loader
