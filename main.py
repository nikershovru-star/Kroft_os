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
from services import VaultStreamCrawler, GraphQueryEngine

from cli.parser import parse_args
from cli.commands import cmd_init, cmd_crawl, cmd_query, cmd_status, cmd_stop, cmd_repl


def build_container(vault_path: str) -> DependencyContainer:
    """Composition root: register ports + concrete adapters + services.

    Adapters (LocalFileSystemAdapter) are referenced HERE only; commands
    receive fully-wired components via container.resolve(...).
    """
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault_path))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"),
            c.resolve("IEventBus"),
            c.resolve("IGraphBuilder"),
            vault_path,
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(c.resolve("IGraphBuilder")),
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
    elif args.command == "status":
        cmd_status(args, build_container(args.vault))
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "repl":
        cmd_repl(args, build_container(args.vault))


if __name__ == "__main__":
    main()
