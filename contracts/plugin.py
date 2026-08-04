"""IPlugin — plugin extension port (Stage 25).

KROFT_OS stops being a monolith: third-party code can add CLI commands,
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

Stage 40 adds agent-extension hooks:
  register_agent_tools(registry)   - register custom agent tools into ToolRegistry.
  register_agent_patterns()        - return list of (regex, [(tool, matcher), ...]).

Architecture contract: stdlib (abc, typing) only.

---

ТЗ-PLUGIN-01 (ADR-071) EXTENSION (К5: IPlugin уже существовал как CLI/export boundary,
Stage 25 — НЕ дублируем; вводим отдельный invoke-capable под-порт ICapabilityPlugin +
IPluginRegistry поверх него). Плагины-обёртки над существующими портами
(ISearchService / IResearchService) реализуют ICapabilityPlugin и регистрируются в
ReferencePluginRegistry — детерминированно, LLM-free, standalone (Флаг C: НЕ в build_kernel).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


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


class Plugin:
    """Base class for KROFT_OS plugins (Stage 40: agent extension hooks).

    Concrete (non-abstract) so plugin authors may subclass and override only
    the hooks they need. Runtime imports are avoided (stdlib-only contract):
    ``ToolRegistry`` is referenced only for type hints under TYPE_CHECKING.
    """

    def register_exporters(self, container: Any) -> None:
        """Stage 25: register custom export formats."""
        pass

    def register_agent_tools(self, registry: Any) -> None:
        """Stage 40: register custom agent tools."""
        pass

    def register_agent_patterns(
        self,
    ) -> List[Tuple[str, List[Tuple[str, Callable[[Any], Dict[str, Any]]]]]]:
        """Stage 40: return list of (regex, [(tool_name, matcher_fn), ...])."""
        return []


# ===========================================================================
# ТЗ-PLUGIN-01 (ADR-071): capability-plugin registry (К5 EXTENSION, not duplicate)
# ===========================================================================


class PluginInvocationError(Exception):
    """Raised when a plugin id is unknown or its invoke() fails."""


@dataclass(frozen=True)
class PluginResult:
    """Outcome of a plugin invocation (frozen VO, real types — Флаг LLM-01)."""
    ok: bool
    payload: Any = None
    error: Optional[str] = None


@dataclass(frozen=True)
class PluginManifest:
    """Static descriptor of a registered plugin (frozen VO)."""
    id: str
    name: str
    capabilities: Tuple[str, ...]


class ICapabilityPlugin(abc.ABC):
    """Invoke-capable plugin port (ТЗ-PLUGIN-01).

    Distinct from the CLI/export ``IPlugin`` (Stage 25): this boundary is for
    discoverable, invocable capabilities behind a registry. one-port-per-boundary
    (K5): we do NOT add invoke to the existing CLI ``IPlugin`` (that would change
    its abstractmethod contract and break plugin_loader / test_plugins).
    """

    @property
    @abc.abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def capabilities(self) -> Tuple[str, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def invoke(self, args: Any) -> PluginResult:
        """Execute the plugin capability. Deterministic; read-only w.r.t. HARD/FSM."""
        raise NotImplementedError


class IPluginRegistry(abc.ABC):
    """Deterministic registry of ICapabilityPlugin instances (ТЗ-PLUGIN-01).

    register/list/get/invoke are deterministic (I-09). Unknown-id invoke ->
    PluginResult(ok=False) (negative, no raise required by caller). Plugins are
    read-only w.r.t. HARD/FSM/contracts (O1).
    """

    @abc.abstractmethod
    def register(self, plugin: ICapabilityPlugin) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def unregister(self, plugin_id: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def list(self) -> List[PluginManifest]:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, plugin_id: str) -> Optional[ICapabilityPlugin]:
        raise NotImplementedError

    @abc.abstractmethod
    def has(self, plugin_id: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def invoke(self, plugin_id: str, args: Any = None) -> PluginResult:
        raise NotImplementedError
