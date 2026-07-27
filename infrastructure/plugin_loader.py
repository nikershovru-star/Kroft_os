"""PluginLoader — filesystem plugin discovery (Stage 25).

Scans a plugin directory for ``*.py`` files, imports each one by file path
(importlib.util — NO sys.path pollution) and instantiates its top-level
``class Plugin``. Loading is fail-soft: a broken plugin file is recorded in
``self.errors`` and skipped; it can NEVER take the core CLI down.

Duck-typed on purpose: ``Plugin`` does not have to subclass
``contracts.IPlugin`` (plugin files live OUTSIDE the project tree and may
have zero project imports). Each of the three hooks is applied only if
present and callable.

Architecture contract: contracts + stdlib (importlib, os, sys, typing).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, List, Tuple


class PluginLoader:
    """Discover, import and apply plugins from a directory."""

    def __init__(self, plugin_dir: str) -> None:
        self._dir = plugin_dir
        self.plugins: List[Any] = []          # instantiated Plugin objects
        self.errors: List[Tuple[str, str]] = []  # (filename, error text)

    # ----- discovery -----
    def load(self) -> List[Any]:
        """Import every ``*.py`` in the dir; instantiate ``Plugin``.

        Missing/invalid dir -> [] (never raises). Files without a top-level
        ``Plugin`` class, or whose import/instantiation raises, are recorded
        in ``self.errors`` and skipped. Deterministic order (sorted names).
        """
        self.plugins = []
        self.errors = []
        try:
            entries = sorted(os.listdir(self._dir))
        except OSError:
            return self.plugins
        for name in entries:
            if not name.endswith(".py") or name.startswith("_"):
                continue
            path = os.path.join(self._dir, name)
            try:
                plugin = self._load_one(name, path)
            except Exception as exc:  # fail-soft: never take the CLI down
                self.errors.append((name, f"{type(exc).__name__}: {exc}"))
                continue
            if plugin is None:
                self.errors.append((name, "no top-level 'class Plugin' found"))
                continue
            self.plugins.append(plugin)
        return self.plugins

    def _load_one(self, name: str, path: str) -> Any:
        mod_name = f"knowledgeos_plugin_{name[:-3]}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot build import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules for the exec duration (dataclasses etc.
        # need it); leave it registered — harmless, namespaced module name.
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None or not isinstance(plugin_cls, type):
            return None
        return plugin_cls()

    # ----- application (each hook optional + fail-soft) -----
    def apply_commands(self, subparsers: Any) -> None:
        """Call register_commands(subparsers) on every plugin that has it."""
        for p in self.plugins:
            hook = getattr(p, "register_commands", None)
            if callable(hook):
                try:
                    hook(subparsers)
                except Exception as exc:
                    self.errors.append(
                        (type(p).__module__, f"register_commands: {exc}")
                    )

    def apply_exporters(self, container: Any) -> None:
        """Call register_exporters(container) on every plugin that has it."""
        for p in self.plugins:
            hook = getattr(p, "register_exporters", None)
            if callable(hook):
                try:
                    hook(container)
                except Exception as exc:
                    self.errors.append(
                        (type(p).__module__, f"register_exporters: {exc}")
                    )

    def notify_crawl_complete(self, graph: Any) -> None:
        """Call on_crawl_complete(graph) on every plugin that has it."""
        for p in self.plugins:
            hook = getattr(p, "on_crawl_complete", None)
            if callable(hook):
                try:
                    hook(graph)
                except Exception as exc:
                    self.errors.append(
                        (type(p).__module__, f"on_crawl_complete: {exc}")
                    )
