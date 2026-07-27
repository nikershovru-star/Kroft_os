"""KnowledgeOS v5 entrypoint.

Wires concrete adapters through the DI container (the ONLY place adapters are
referenced) and dispatches CLI commands. Run: `python main.py <command>`.
"""
from __future__ import annotations

import sys as _sys

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
    PluginLoader,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.exporters import export_dot, export_json, export_gexf
from adapters.file_watcher import FileWatcher
from adapters.http_server import KnowledgeOSServer
from adapters.embedding import MockEmbeddingAdapter

from cli.parser import parse_args
from cli.commands import (
    cmd_init, cmd_crawl, cmd_query, cmd_status, cmd_stop, cmd_repl, cmd_search, cmd_export, cmd_watch, cmd_serve, cmd_semantic, cmd_hybrid, cmd_desktop, cmd_agent, cmd_schedule,
)
from services import VaultStreamCrawler, GraphQueryEngine, CrawlStateTracker, ContentIndex, WatchService, SemanticIndex, DesktopService, DesktopOrchestrator, ToolRegistry, AgentService, SchedulerService
from adapters.desktop_adapter import MockDesktopAdapter
from adapters.agent_adapter import RuleBasedAgentAdapter


def build_container(vault_path: str, loader=None, desktop_adapter: str = "mock") -> DependencyContainer:
    """Composition root: register ports + concrete adapters + services.

    Adapters (LocalFileSystemAdapter) are referenced HERE only; commands
    receive fully-wired components via container.resolve(...).

    Stage 17: a CrawlStateTracker is wired into the crawler, so `crawl`
    (batch CLI and REPL alike) is INCREMENTAL — a second crawl with no
    vault changes returns {"status": "up_to_date", "files_scanned": 0}.
    """
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault_path))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    # Stage 18: singleton ContentIndex — the crawler WRITES to it, the query
    # engine READS from it (same shared-instance convention as IGraphBuilder).
    c.register_instance("ContentIndex", ContentIndex())
    # Stage 29: shared SemanticIndex (crawler writes, engine reads) + the
    # default deterministic Mock embedding (real OpenAI adapter is opt-in).
    c.register_instance("SemanticIndex", SemanticIndex())
    c.register_instance("Embedding", MockEmbeddingAdapter())
    # Stage 31/36: Desktop capability. Default Mock (zero regression);
    # opt-in PyAutoGUI via --desktop-adapter flag or DESKTOP_ADAPTER env var.
    if desktop_adapter == "pyautogui":
        from adapters.desktop_adapter import PyAutoGUIAdapter
        c.register_instance("IDesktop", PyAutoGUIAdapter())
    else:
        c.register_instance("IDesktop", MockDesktopAdapter())
    c.register_factory(
        "DesktopService",
        lambda: DesktopService(c.resolve("IDesktop")),
    )
    # Stage 32: DesktopOrchestrator bridges search + desktop action
    c.register_factory(
        "DesktopOrchestrator",
        lambda: DesktopOrchestrator(
            c.resolve("GraphQueryEngine"),
            c.resolve("DesktopService"),
            c.resolve("IFileSystem"),
            vault_path,
        ),
    )
    # Stage 33: Hermes Agent — tool registry + rule-based intent router
    c.register_instance("ToolRegistry", ToolRegistry())
    c.register_factory(
        "AgentService",
        lambda: _wire_agent(c),
    )
    c.register_factory(
        "IAgent",
        lambda: RuleBasedAgentAdapter(c.resolve("AgentService")),
    )
    c.register_factory(
        "CrawlStateTracker",
        lambda: CrawlStateTracker(c.resolve("IFileSystem"), ".crawl_state.json"),
    )
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"),
            c.resolve("IEventBus"),
            c.resolve("IGraphBuilder"),
            vault_path,
            tracker=c.resolve("CrawlStateTracker"),
            index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(
            c.resolve("IGraphBuilder"),
            index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    # Stage 23: graph exporters registered as instances. The composition root
    # (main.py) is the ONLY place adapters are referenced; cli/ resolves them
    # by name, so cli/ stays arch-clean (it must NOT import adapters directly).
    c.register_instance("export_dot", export_dot)
    c.register_instance("export_json", export_json)
    c.register_instance("export_gexf", export_gexf)
    # Stage 27: file watcher (adapter) + watch service. The watcher is an
    # adapter, so it is referenced HERE (composition root) only; cli/services
    # resolve it by name. WatchService gets the crawler + watcher injected.
    c.register_factory(
        "FileWatcher",
        lambda: FileWatcher(vault_path, interval=2.0),
    )
    c.register_factory(
        "WatchService",
        lambda: WatchService(
            c.resolve("VaultStreamCrawler"),
            c.resolve("FileWatcher"),
            kernel=None,  # cmd_watch injects the live Kernel after build
        ),
    )
    # Stage 22: HTTP server adapter (stdlib http.server). Registered HERE in
    # the composition root only; cli/ resolves it by name and overrides
    # _host/_port before start() -- cli/ must NOT import adapters directly.
    c.register_factory(
        "KnowledgeOSServer",
        lambda: KnowledgeOSServer(c, host="127.0.0.1", port=8080),
    )
    # Stage 25: plugin system. The loader (if any) merges plugin exporters
    # into the container and is itself registered so cli/ can fire hooks
    # (on_crawl_complete) and report plugin errors without importing
    # infrastructure loading machinery.
    c.register_instance("PluginLoader", loader)
    if loader is not None:
        loader.apply_exporters(c)
    # Stage 35: Task Scheduler (executor wired to IAgent.execute)
    c.register_instance("SchedulerService", SchedulerService())
    _wire_scheduler(c)
    return c


def _wire_agent(container: DependencyContainer) -> AgentService:
    """Register all available tools in the ToolRegistry and return AgentService.

    Lives in the composition root (main.py) so it may resolve exporters and
    services by name without any service->service or cli->adapters imports.
    """
    registry: ToolRegistry = container.resolve("ToolRegistry")
    engine: GraphQueryEngine = container.resolve("GraphQueryEngine")
    orch: DesktopOrchestrator = container.resolve("DesktopOrchestrator")
    desktop: DesktopService = container.resolve("DesktopService")

    # Search tools
    registry.register("list_notes", lambda query, top_k: orch.list_notes(query, top_k),
                      "List note candidates via hybrid search")
    registry.register("open_note", lambda query, top_k: orch.open_note(query, top_k),
                      "Open top-1 note via hybrid search")

    # Graph analytics
    registry.register("most_central", lambda: engine.centrality(),
                      "Return centrality metrics for all nodes")
    registry.register("list_orphans", lambda: engine.search("is:orphan"),
                      "List orphan nodes")

    # Export (exporters registered as instances in build_container)
    def _export_graph(fmt: str):
        g = container.resolve("IGraphBuilder").get_graph()
        if fmt == "dot":
            return container.resolve("export_dot")(g)
        elif fmt == "json":
            return container.resolve("export_json")(g)
        elif fmt == "gexf":
            return container.resolve("export_gexf")(g)
        return {"error": f"unknown format {fmt}"}
    registry.register("export_graph", _export_graph, "Export graph to dot/json/gexf")

    # Desktop
    registry.register("screenshot", lambda: {"size": len(desktop.capture_screen())},
                      "Capture screen and return PNG size")
    registry.register("cursor_position", lambda: {"x": desktop.where_is_cursor()[0], "y": desktop.where_is_cursor()[1]},
                      "Return cursor coordinates")

    return AgentService(registry)


def _wire_scheduler(container: DependencyContainer) -> None:
    """Wire the scheduler's executor to the Hermes agent (composition root only)."""
    sched: SchedulerService = container.resolve("SchedulerService")
    agent = container.resolve("IAgent")
    sched.set_executor(lambda cmd: agent.execute(cmd))


def _prescan_plugin_dir(argv) -> str | None:
    """Extract --plugin-dir BEFORE the real parser exists (chicken-and-egg:
    plugins must register their subcommands into the parser itself)."""
    import argparse as _argparse
    pre = _argparse.ArgumentParser(add_help=False)
    pre.add_argument("--plugin-dir", default=None)
    known, _ = pre.parse_known_args(argv)
    return known.plugin_dir


def _prescan_desktop_adapter(argv) -> str:
    """Extract --desktop-adapter from anywhere in argv (Stage 36).

    Works regardless of position (before or after the subcommand). The flag
    and its value are STRIPPED from *argv* (mutated in place) so the real
    parser never chokes on an unknown global flag after the subcommand.
    Falls back to the DESKTOP_ADAPTER env var, then "mock".
    """
    import argparse as _argparse
    import os as _os
    pre = _argparse.ArgumentParser(add_help=False)
    pre.add_argument("--desktop-adapter", dest="desktop_adapter", default=None)
    known, _ = pre.parse_known_args(argv)
    # strip the flag (and its value) from argv so parse_args won't see it
    if known.desktop_adapter is not None:
        try:
            i = argv.index("--desktop-adapter")
            # value may be attached (--desktop-adapter=pyautogui) or separate
            if "=" in argv[i]:
                argv.pop(i)
            else:
                argv.pop(i); argv.pop(i)  # remove flag + value
        except (ValueError, IndexError):
            pass
    if known.desktop_adapter in ("mock", "pyautogui"):
        return known.desktop_adapter
    env = _os.environ.get("DESKTOP_ADAPTER")
    if env in ("mock", "pyautogui"):
        return env
    return "mock"


def main(argv=None) -> None:
    # Stage 36: normalize to a mutable list so --desktop-adapter can be
    # stripped in place before the real parser runs.
    if argv is None:
        argv = _sys.argv[1:]
    else:
        argv = list(argv)
    # Stage 25: load plugins first so their subcommands exist at parse time.
    plugin_dir = _prescan_plugin_dir(argv)
    # Stage 36: extract --desktop-adapter (works in any position), default mock.
    desktop_adapter = _prescan_desktop_adapter(argv)
    loader = None
    if plugin_dir is not None:
        loader = PluginLoader(plugin_dir)
        loader.load()
        for fname, err in loader.errors:
            print(f"[plugin] {fname}: {err}", file=_sys.stderr)
    args = parse_args(argv, loader=loader)
    build = lambda: build_container(args.vault, loader=loader,
                                    desktop_adapter=desktop_adapter)
    # Plugin-registered subcommands carry their handler via set_defaults(func=...).
    if getattr(args, "func", None) is not None and args.command not in _BUILTIN_COMMANDS:
        # A plugin command may omit --vault entirely -- default to cwd so the
        # container can still be built (LocalFileSystemAdapter needs a path).
        plugin_vault = getattr(args, "vault", None) or "."
        args.func(args, build_container(plugin_vault, loader=loader))
        return
    if args.command == "init":
        cmd_init(args)
    elif args.command == "crawl":
        cmd_crawl(args, build())
    elif args.command == "query":
        cmd_query(args, build())
    elif args.command == "search":
        cmd_search(args, build())
    elif args.command == "status":
        cmd_status(args, build())
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "repl":
        cmd_repl(args, build())
    elif args.command == "export":
        cmd_export(args, build())
    elif args.command == "watch":
        cmd_watch(args, build())
    elif args.command == "serve":
        cmd_serve(args, build())
    elif args.command == "semantic":
        cmd_semantic(args, build())
    elif args.command == "hybrid":
        cmd_hybrid(args, build())
    elif args.command == "desktop":
        cmd_desktop(args, build())
    elif args.command == "agent":
        cmd_agent(args, build())
    elif args.command == "schedule":
        cmd_schedule(args, build())


_BUILTIN_COMMANDS = {
    "init", "crawl", "query", "search", "status", "stop", "repl",
    "export", "watch", "serve", "semantic", "hybrid", "desktop", "agent", "schedule",
}


if __name__ == "__main__":
    main()
