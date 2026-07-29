"""KnowledgeOS v5 entrypoint.

Wires concrete adapters through the DI container (the ONLY place adapters are
referenced) and dispatches CLI commands. Run: `python main.py <command>`.
"""
from __future__ import annotations

import os as _os
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
from services import VaultStreamCrawler, GraphQueryEngine, CrawlStateTracker, ContentIndex, WatchService, SemanticIndex, DesktopService, DesktopOrchestrator, ToolRegistry, AgentService, SchedulerService, SessionStore
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
    # Stage 39: Agent Session Store (survives restarts)
    data_dir = _os.path.join(vault_path, ".kos")
    c.register_instance("SessionStore", SessionStore(
        persistence_path=_os.path.join(data_dir, "session.json"),
    ))
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
            fs=c.resolve("IFileSystem"),
            snapshot_path=_os.path.join(vault_path, ".kos", "graph.json"),
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
    # Stage 38: Scheduler persistence (JSON snapshot + JSON Lines execution log)
    data_dir = _os.path.join(vault_path, ".kos")
    sched = SchedulerService(
        persistence_path=_os.path.join(data_dir, "scheduler.json"),
        log_path=_os.path.join(data_dir, "scheduler.log"),
    )
    c.register_instance("SchedulerService", sched)
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
    # Stage 37: export without the 'graph to' connective (spec v5.0: export <fmt> [query])
    registry.register("export_format", _export_graph, "Export graph as dot/json/gexf")

    # Desktop
    registry.register("screenshot", lambda: {"size": len(desktop.capture_screen())},
                      "Capture screen and return PNG size")
    registry.register("cursor_position", lambda: {"x": desktop.where_is_cursor()[0], "y": desktop.where_is_cursor()[1]},
                      "Return cursor coordinates")
    # Stage 37: NL desktop intents (spec v5.0)
    registry.register("desktop_click", lambda x, y: (desktop.click_at(int(x), int(y)) or {"ok": True, "x": int(x), "y": int(y)}),
                      "Click at screen (x, y)")
    registry.register("desktop_type", lambda text: (desktop.type_text(text) or {"ok": True}),
                      "Type text via keyboard")
    registry.register("desktop_open_app", lambda name: (desktop.launch(name) or {"ok": True, "app": name}),
                      "Open an application by name")

    # Capabilities (spec v5.0: 'что ты умеешь')
    def _capabilities():
        return {
            "actions": [
                "find", "open", "show", "export", "desktop",
                "schedule", "centrality", "orphan",
            ],
            "hint": "Try: find <topic>, open <file>, show <topic>, export <dot|json|gexf>, "
                    "desktop cursor|screenshot|click x y|type <text>|open_app <name>",
        }
    registry.register("capabilities", _capabilities, "List available agent actions")

    # Show (spec v5.0: render note content inline)
    registry.register("show_note", lambda query, top_k=1: orch.show_note(query, top_k),
                      "Show top note content inline")

    # Stage 43: graph reasoning tools
    def _graph_neighbors(query: str, direction: str = "both", depth: int = 1):
        results = engine.hybrid_search(query, top_k=1)
        if not results:
            return {"error": "no results", "query": query}
        nid = results[0][0]
        return {"ok": True, "node": nid, "neighbors": engine.get_neighbors(nid, direction, depth)}

    registry.register("graph_neighbors", _graph_neighbors,
                      "Graph neighbors of a note (direction: in/out/both, depth: int)")

    def _graph_path(from_query: str, to_query: str):
        a = engine.hybrid_search(from_query, top_k=1)
        b = engine.hybrid_search(to_query, top_k=1)
        if not a or not b:
            return {"error": "node not found"}
        path = engine.shortest_path(a[0][0], b[0][0])
        return {
            "ok": True,
            "from": a[0][0],
            "to": b[0][0],
            "path": path,
            "length": len(path) - 1 if path else -1,
        }

    registry.register("graph_path", _graph_path,
                      "Shortest path between two notes")

    def _graph_cluster(query: str, k: int = 5):
        results = engine.hybrid_search(query, top_k=1)
        if not results:
            return {"error": "no results", "query": query}
        return {"ok": True, "node": results[0][0], "cluster": engine.get_cluster(results[0][0], k)}

    registry.register("graph_cluster", _graph_cluster,
                      "Personalized PageRank cluster around a note")

    # Stage 44: graph mutation tools
    def _graph_link(from_query: str, to_query: str, relation: str = "links"):
        return engine.add_link(from_query, to_query, relation)
    registry.register("graph_link", _graph_link, "Create a link between two notes")

    def _graph_unlink(from_query: str, to_query: str):
        return engine.remove_link(from_query, to_query)
    registry.register("graph_unlink", _graph_unlink, "Remove a link between two notes")

    def _graph_tag(query: str, tag: str):
        return engine.add_tag(query, tag)
    registry.register("graph_tag", _graph_tag, "Add a tag to a note")

    def _graph_untag(query: str, tag: str):
        return engine.remove_tag(query, tag)
    registry.register("graph_untag", _graph_untag, "Remove a tag from a note")

    # Stage 45: graph link recommendations
    def _graph_suggest(query: str, top_k: int = 5):
        results = engine.suggest_links(query, top_k=top_k)
        return {"ok": True, "query": query, "suggestions": results}
    registry.register("graph_suggest", _graph_suggest,
                      "Suggest missing links for a note (graph+content hybrid)")

    # Stage 46: graph analytics & health
    def _graph_stats():
        return engine.graph_stats()
    registry.register("graph_stats", _graph_stats, "Graph statistics")

    def _graph_orphans():
        return {"ok": True, "orphans": engine.orphan_nodes()}
    registry.register("graph_orphans", _graph_orphans, "List orphan notes")

    def _graph_central(k: int = 5):
        return {"ok": True, "top": engine.top_central(k=k)}
    registry.register("graph_central", _graph_central, "Top central notes by pagerank/degree")

    def _graph_health():
        return engine.graph_health()
    registry.register("graph_health", _graph_health, "Graph health check")

    # Stage 47: graph snapshot persistence
    def _save_graph():
        return engine.save_graph()
    registry.register("save_graph", _save_graph, "Explicitly persist graph to disk")

    def _auto_save(enabled: bool):
        engine.set_auto_snapshot(enabled)
        return engine.auto_snapshot_status()
    registry.register("auto_save", _auto_save, "Toggle auto-snapshot after mutations")

    # Stage 48: graph-enhanced hybrid search
    def _enhanced_search(query: str):
        results = engine.graph_enhanced_search(query)
        return {"ok": True, "query": query, "count": len(results), "results": results}
    registry.register("enhanced_search", _enhanced_search,
                      "Graph-enhanced hybrid search (semantic + graph proximity + recency)")

    # Stage 49: graph constraints & auto-fix
    def _validate_graph():
        return engine.validate_graph()
    registry.register("validate_graph", _validate_graph, "Validate graph constraints")

    def _find_broken_links():
        return {"ok": True, "broken": engine.find_broken_links()}
    registry.register("find_broken_links", _find_broken_links, "Find edges pointing to missing nodes")

    def _fix_graph():
        return engine.fix_graph()
    registry.register("fix_graph", _fix_graph, "Auto-fix graph issues (tag orphans, remove broken links)")

    # Stage 51: graph-driven review queue & compound filtering
    def _review_queue(top_k: int = 10):
        return {"ok": True, "queue": engine.review_queue(top_k=top_k)}
    registry.register("review_queue", _review_queue,
                      "Prioritized review queue (orphans, stale, untagged, peripheral)")

    def _compound_query(**filters):
        return {"ok": True, "matches": engine.compound_query(**filters)}
    registry.register("compound_query", _compound_query,
                      "Compound graph query (tags, degree, orphan, recency, linked_to)")

    # Stage 50: graph temporal audit log
    def _audit_log():
        return {"ok": True, "log": engine.get_audit_log()}
    registry.register("audit_log", _audit_log, "Show graph temporal audit log")

    def _recent_changes():
        return {"ok": True, "log": engine.get_audit_log()[-10:]}
    registry.register("recent_changes", _recent_changes, "Show recent graph changes")

    def _mutations_since(ts_min: float):
        return {"ok": True, "mutations": engine.mutations_since(ts_min)}
    registry.register("mutations_since", _mutations_since, "Graph mutations since timestamp")

    # Stage 52: graph-driven workflows
    def _research_topic(query: str):
        return engine.research_topic(query)
    registry.register("research_topic", _research_topic,
                      "Research a topic through the knowledge graph (neighbors, gaps, lateral links)")

    def _bridge_topics(from_query: str, to_query: str):
        return engine.bridge_topics(from_query, to_query)
    registry.register("bridge_topics", _bridge_topics,
                      "Bridge two topics via shortest path or common neighbors")

    def _expand_knowledge(query: str):
        return engine.expand_knowledge(query)
    registry.register("expand_knowledge", _expand_knowledge,
                      "Expand knowledge from a seed via cluster analysis and link suggestions")

    # Stage 53: graph-based agent context memory
    def _record_user_query(session_id: str, query_text: str, hit_nodes: List[str], intent: str = "unknown"):
        return engine.record_user_query(session_id, query_text, hit_nodes, intent)
    registry.register("record_user_query", _record_user_query,
                      "Record user query into graph context memory")

    def _get_session_context(session_id: str, depth: int = 2):
        return engine.get_session_context(session_id, depth)
    registry.register("get_session_context", _get_session_context,
                      "Retrieve session context from graph memory")

    def _suggest_next(session_id: str, top_n: int = 3):
        return engine.suggest_next(session_id, top_n)
    registry.register("suggest_next", _suggest_next,
                      "Proactive suggestions based on interest graph")

    def _get_personalized_summary(session_id: str, target_node: str):
        return engine.get_personalized_summary(session_id, target_node)
    registry.register("get_personalized_summary", _get_personalized_summary,
                      "Personalized node summary with session context")

    # Stage 54: graph health monitor
    registry.register("graph_health_report", engine.graph_health_report,
                      "Full graph health diagnostic")

    def _find_duplicate_candidates(threshold: float = 0.8):
        return engine.find_duplicate_candidates(threshold)
    registry.register("find_duplicate_candidates", _find_duplicate_candidates,
                      "Find duplicate node candidates")

    def _cleanup_orphans(dry_run: bool = True):
        return engine.cleanup_orphans(dry_run)
    registry.register("cleanup_orphans", _cleanup_orphans,
                      "Remove orphaned content nodes")

    def _merge_nodes(from_node: str, to_node: str, dry_run: bool = True):
        return engine.merge_nodes(from_node, to_node, dry_run)
    registry.register("merge_nodes", _merge_nodes,
                      "Merge two graph nodes into one")

    session = container.resolve("SessionStore")
    # Stage 40: plugin agent extensions (tools + patterns)
    loader = container.try_resolve("PluginLoader")  # None if no plugins loaded
    if loader is not None:
        agent = AgentService(registry, session_store=session)  # pre-create to pass to plugins
        loader.apply_agent_extensions(registry, agent)
        return agent
    return AgentService(registry, session_store=session)


def _wire_scheduler(container: DependencyContainer) -> None:
    """Wire the scheduler's executor to the Hermes agent (composition root only)."""
    sched: SchedulerService = container.resolve("SchedulerService")
    agent = container.resolve("IAgent")
    sched.set_executor(lambda cmd: agent.execute(cmd))


def _prescan_plugin_dir(argv) -> str | None:
    """Extract --plugin-dir from anywhere in argv (Stage 25/40).

    Works regardless of position (before or after the subcommand). The flag
    and its value are STRIPPED from *argv* (mutated in place) so the real
    parser never chokes on an unknown global flag after the subcommand.
    """
    import argparse as _argparse
    pre = _argparse.ArgumentParser(add_help=False)
    pre.add_argument("--plugin-dir", default=None)
    known, _ = pre.parse_known_args(argv)
    if known.plugin_dir is not None:
        try:
            i = argv.index("--plugin-dir")
            if "=" in argv[i]:
                argv.pop(i)
            else:
                argv.pop(i); argv.pop(i)  # remove flag + value
        except ValueError:
            pass
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
