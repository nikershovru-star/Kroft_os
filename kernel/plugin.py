"""Reference plugin registry (ТЗ-PLUGIN-01, ADR-071) — deterministic, LLM-free, standalone.

K1-compliant: stdlib + contracts only. STANDALONE service (Флаг C SEARCH/RESEARCH): constructed
from capability plugins; does NOT wire into ``build_kernel`` and the kernel never depends on it
(K6). No god-factory aggravation (Флаг 1 OBS-01).

Design flags honored:
- I-09 (determinism): storage is a plain dict keyed by plugin id; list() returns manifests
  sorted by id so the order is stable across calls. invoke() is deterministic for a given
  plugin + args.
- O1 (read-only w.r.t. HARD/FSM/contracts): reference plugins only READ via ISearchService /
  IResearchService; they never mutate HARD/FSM/contracts. The registry never mutates plugins.
- Negative handling (K8): unknown-id invoke -> PluginResult(ok=False, error=...); duplicate
  register -> PluginInvocationError (handled, not silent); unregister of unknown id -> no-op.
- Reuse, don't duplicate (K5): SearchPlugin/ResearchPlugin WRAP the existing ISearchService /
  IResearchService ports — they do NOT reimplement search/research.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from contracts.plugin import (
    ICapabilityPlugin,
    IPluginRegistry,
    PluginInvocationError,
    PluginManifest,
    PluginResult,
)


class ReferencePluginRegistry(IPluginRegistry):
    """In-memory deterministic registry of ICapabilityPlugin instances."""

    def __init__(self) -> None:
        self._plugins: Dict[str, ICapabilityPlugin] = {}

    # -- IPluginRegistry ------------------------------------------------
    def register(self, plugin: ICapabilityPlugin) -> None:
        pid = plugin.id
        if pid in self._plugins:
            raise PluginInvocationError(f"duplicate plugin id: {pid}")
        self._plugins[pid] = plugin

    def unregister(self, plugin_id: str) -> None:
        self._plugins.pop(plugin_id, None)  # unknown id -> safe no-op

    def list(self) -> List[PluginManifest]:
        return [p.manifest() for p in sorted(self._plugins.values(), key=lambda p: p.id)]

    def get(self, plugin_id: str) -> Optional[ICapabilityPlugin]:
        return self._plugins.get(plugin_id)

    def has(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def invoke(self, plugin_id: str, args: Any = None) -> PluginResult:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return PluginResult(ok=False, error=f"unknown plugin id: {plugin_id}")
        try:
            return plugin.invoke(args)
        except PluginInvocationError as exc:
            return PluginResult(ok=False, error=str(exc))
        except Exception as exc:  # defensive: a plugin failure must not crash the caller
            return PluginResult(ok=False, error=f"plugin {plugin_id} failed: {exc}")


class _BaseCapabilityPlugin(ICapabilityPlugin):
    """Shared manifest() impl so concrete plugins only declare id/name/caps/invoke."""

    def manifest(self) -> PluginManifest:
        return PluginManifest(id=self.id, name=self.name, capabilities=self.capabilities)


class SearchPlugin(_BaseCapabilityPlugin):
    """Reference plugin WRAPPING ISearchService (К5: reuse, no duplication).

    O1: read-only — invokes search(), never mutates memory/graph/contracts.
    """

    def __init__(self, search, plugin_id: str = "search",
                 name: str = "Knowledge Search",
                 capabilities: Tuple[str, ...] = ("retrieval",)) -> None:
        self._id = plugin_id
        self._name = name
        self._caps = capabilities
        self._search = search

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> Tuple[str, ...]:
        return self._caps

    def invoke(self, args: Any) -> PluginResult:  # args: {"query", "scope"?, "top_k"?}
        if not isinstance(args, dict) or "query" not in args:
            raise PluginInvocationError("search plugin requires args={'query': str, ...}")
        from contracts.i_search import SearchScope
        scope = args.get("scope", SearchScope.ALL)
        top_k = int(args.get("top_k", 5))
        hits = self._search.search(args["query"], scope=scope, top_k=top_k)
        payload = [{"source": h.source, "content": h.content,
                    "confidence": h.confidence.value} for h in hits]
        return PluginResult(ok=True, payload=payload)


class ResearchPlugin(_BaseCapabilityPlugin):
    """Reference plugin WRAPPING IResearchService (К5: reuse, no duplication).

    O1: read-only — runs the research cycle; does NOT write back (write_back defaults off).
    """

    def __init__(self, research, plugin_id: str = "research",
                 name: str = "Knowledge Research",
                 capabilities: Tuple[str, ...] = ("synthesis",)) -> None:
        self._id = plugin_id
        self._name = name
        self._caps = capabilities
        self._research = research

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> Tuple[str, ...]:
        return self._caps

    def invoke(self, args: Any) -> PluginResult:  # args: {"query", "scope"?, "max_findings"?}
        if not isinstance(args, dict) or "query" not in args:
            raise PluginInvocationError("research plugin requires args={'query': str, ...}")
        from contracts.i_research import ResearchGoal
        from contracts.i_search import SearchScope
        scope = args.get("scope", SearchScope.ALL)
        max_findings = int(args.get("max_findings", 5))
        report = self._research.research(
            ResearchGoal(query=args["query"], scope=scope, max_findings=max_findings))
        payload = {
            "summary": report.summary,
            "confidence": report.confidence.value,
            "findings": [h.source for h in report.findings],
        }
        return PluginResult(ok=True, payload=payload)


def build_plugin_registry(*plugins: ICapabilityPlugin) -> ReferencePluginRegistry:
    """Factory: assemble a standalone ReferencePluginRegistry (ТЗ-PLUGIN-01 commit 3, Флаг C).

    Intentionally SEPARATE from ``build_kernel``: the cognitive kernel does NOT depend on the
    plugin registry, and the registry does NOT mutate the kernel. Callers (an external
    agent/API/extension host) construct it directly from capability plugins they already hold.
    The kernel is never touched (god-factory Флаг 1 OBS-01 not aggravated).
    """
    reg = ReferencePluginRegistry()
    for p in plugins:
        reg.register(p)
    return reg
