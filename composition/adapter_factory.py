"""composition/adapter_factory.py — Adapter assembly (Phase B.1).

Точка регистрации конкретных адаптеров (filesystem, exporters, watcher, server,
embedding, desktop). Composition Root — единственное место, где adapters
референсятся; kernel/cli резолвят по имени (arch-gate K1/K6).
"""
from __future__ import annotations

from infrastructure import InMemoryGraphBuilder, InMemoryEventBus
from adapters import LocalFileSystemAdapter
from adapters.exporters import export_dot, export_json, export_gexf
from adapters.file_watcher import FileWatcher
from adapters.http_server import KROFT_OSServer
from adapters.embedding import MockEmbeddingAdapter
from adapters.desktop_adapter import MockDesktopAdapter


def build_core_adapters(vault_path: str, container, desktop_adapter: str = "mock"):
    """Register filesystem, eventbus, graphbuilder, embedding, desktop, exporters."""
    container.register_instance("IFileSystem", LocalFileSystemAdapter(vault_path))
    container.register_instance("IEventBus", InMemoryEventBus())
    container.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    container.register_instance("Embedding", MockEmbeddingAdapter())
    if desktop_adapter == "pyautogui":
        from adapters.desktop_adapter import PyAutoGUIAdapter
        container.register_instance("IDesktop", PyAutoGUIAdapter())
    else:
        container.register_instance("IDesktop", MockDesktopAdapter())
    container.register_instance("export_dot", export_dot)
    container.register_instance("export_json", export_json)
    container.register_instance("export_gexf", export_gexf)


def build_watcher(vault_path: str, container):
    container.register_factory("FileWatcher", lambda: FileWatcher(vault_path, interval=2.0))


def build_server(container):
    container.register_factory("KROFT_OSServer", lambda: KROFT_OSServer(container, host="127.0.0.1", port=8080))
