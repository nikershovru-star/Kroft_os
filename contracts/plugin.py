"""IPlugin — plugin extension port (Stage 25).

KnowledgeOS stops being a monolith: third-party code can add CLI commands,
graph exporters and crawl hooks WITHOUT touching main.py / cli/commands.py.

Convention (enforced by infrastructure.PluginLoader):
  * a plugin is a single ``*.py`` file inside the plugin directory
    (``--plugin-dir``), containing a top-level ``class Plugin``;
  * subclassing ``contracts.IPlugin`` is RECOMMENDED (gets you the contract
    check for free) but NOT required — the loader duck-types the three hooks,
    so a plugin file has zero mandatory imports from the project.

Hooks (all optional at runtime — the loader tolerates missing ones):
  register_commands(parser)    - ``parser`` is the argparse SUBPARSERS action
                                 (has ``.add_parser(name, ...)``); use
                                 ``sub.set_defaults(func=handler)`` where
                                 ``handler(args, container)`` is the command
                                 implementation.
  register_exporters(container)- register export functions into the DI
                                 container: ``container.register_instance(
                                 "export_<fmt>", fn)`` makes
                                 ``main.py export --format <fmt>`` work.
  on_crawl_complete(graph)     - called after each successful batch ``crawl``
                                 with the graph dict ({"nodes": ..., "edges":
                                 ...}); side-effect hook (stats, sync, ...).

Architecture contract: stdlib (abc, typing) only.
"""
from __future__ import annotations

import abc
from typing import Any, Dict


class IPlugin(abc.ABC):
    """Extension port: CLI commands + exporters + crawl hook."""

    @abc.abstractmethod
    def register_commands(self, parser: Any) -> None:
        """Add argparse subcommands. ``parser`` is the subparsers action."""
        raise NotImplementedError

    @abc.abstractmethod
    def register_exporters(self, container: Any) -> None:
        """Register ``export_<fmt>`` callables into the DI container."""
        raise NotImplementedError

    @abc.abstractmethod
    def on_crawl_complete(self, graph: Dict[str, Any]) -> None:
        """Called after a successful batch crawl with the graph dict."""
        raise NotImplementedError
