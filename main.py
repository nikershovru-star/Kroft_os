"""KnowledgeOS v5 entrypoint.

Wires concrete adapters through the DI container (the ONLY place adapters are
referenced) and dispatches CLI commands. Run: `python main.py <command>`.
"""
from __future__ import annotations

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.exporters import export_dot, export_json, export_gexf
from adapters.file_watcher import FileWatcher
from adapters.http_server import KnowledgeOSServer

from cli.parser import parse_args
from cli.commands import (
    cmd_init, cmd_crawl, cmd_query, cmd_status, cmd_stop, cmd_repl, cmd_search, cmd_export, cmd_watch, cmd_serve,
)
from services import VaultStreamCrawler, GraphQueryEngine, CrawlStateTracker, ContentIndex, WatchService


def build_container(vault_path: str) -> DependencyContainer:
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
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(
            c.resolve("IGraphBuilder"),
            index=c.resolve("ContentIndex"),
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
    return c


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.command == "init":
        cmd_init(args)
    elif args.command == "crawl":
        cmd_crawl(args, build_container(args.vault))
    elif args.command == "query":
        cmd_query(args, build_container(args.vault))
    elif args.command == "search":
        cmd_search(args, build_container(args.vault))
    elif args.command == "status":
        cmd_status(args, build_container(args.vault))
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "repl":
        cmd_repl(args, build_container(args.vault))
    elif args.command == "export":
        cmd_export(args, build_container(args.vault))
    elif args.command == "watch":
        cmd_watch(args, build_container(args.vault))
    elif args.command == "serve":
        cmd_serve(args, build_container(args.vault))


if __name__ == "__main__":
    main()
