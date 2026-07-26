"""CLI command implementations.

Each command owns its Kernel lifecycle: build (or receive) a DI container,
drive Kernel init -> start -> stop, print a JSON result to stdout. There is NO
long-running daemon -- every invocation spins the Kernel up and tears it down.

Stage 15: every command first loads ``knowledgeos.yaml`` (or .json) from the
vault via the ``IFileSystem`` port and merges it with CLI args, so the config
file closes the historical limitation "no config file -- all params via CLI".
cli/ never imports adapters directly; it resolves ports through the container.
"""
from __future__ import annotations
import atexit
import asyncio
import json
import os
from typing import Optional

from kernel import Kernel
from infrastructure import ConfigLoader
from services import VaultStreamCrawler, GraphQueryEngine
from cli.repl import KnowledgeOSRepl

# Template written by `init` if no config exists yet.
_CONFIG_TEMPLATE = """\
# KnowledgeOS v5 Configuration
vault: .  # relative to this file's directory (the vault root)
autosave_interval: 60  # seconds; 0 to disable periodic autosave
features:
  extract_tags: true
  extract_wiki_links: true
  full_text_index: false  # not yet implemented
"""


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _resolve_config(args, container) -> dict:
    """Load vault config and merge with CLI args. Returns effective config.

    The IFileSystem registered in the container is rooted at the vault (see
    main.build_container), so the config file is always read from the vault
    root via a relative name. The ``vault:`` key inside the file is resolved
    relative to that root; CLI --vault, when present, takes precedence.
    """
    loader = ConfigLoader()
    fs = container.resolve("IFileSystem")
    raw = loader.load(".", fs)
    return loader.merge_with_cli(args, raw)


def cmd_init(args, container: Optional[object] = None) -> None:
    """Create <vault>/ and <vault>/data/ and a knowledgeos.yaml template."""
    vault = args.vault or "."
    os.makedirs(vault, exist_ok=True)
    data_dir = os.path.join(vault, "data")
    os.makedirs(data_dir, exist_ok=True)
    config_path = os.path.join(vault, "knowledgeos.yaml")
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as fh:
            fh.write(_CONFIG_TEMPLATE)
    _dump({"created": [vault, data_dir], "config": config_path})


def cmd_crawl(args, container) -> None:
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()
    k.start()
    # Stage 14: guarantee a final snapshot on graceful exit
    # (sys.exit / normal return / KeyboardInterrupt / SIGTERM).
    atexit.register(lambda: k.stop())
    crawler = container.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())
    k.stop()  # persists snapshot before teardown
    _dump(crawler.get_stats())


def cmd_query(args, container) -> None:
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()  # restores graph from snapshot if present
    # Stage 14: atexit guarantees snapshot on graceful exit if the command
    # mutates/owns the graph lifecycle.
    atexit.register(lambda: k.stop())
    engine = container.resolve("GraphQueryEngine")
    if args.backlinks is not None:
        result = engine.backlinks(args.backlinks)
    elif args.path is not None:
        result = engine.path(args.path[0], args.path[1])
    elif args.orphans:
        result = engine.orphan_nodes()
    elif args.tags is not None:
        result = engine.nodes_by_tag(args.tags)
    else:
        result = engine.stats()
    _dump(result)


def cmd_status(args, container) -> None:
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()  # restores graph from snapshot if present
    atexit.register(lambda: k.stop())
    graph = container.resolve("IGraphBuilder")
    _dump({
        "state": k.state.name,
        "graph_nodes": len(graph.get_graph()["nodes"]),
        "graph_edges": len(graph.get_graph()["edges"]),
    })


def cmd_search(args, container) -> None:
    """Full-text search (Stage 21 DSL / Stage 20 --fuzzy).

       Examples: 'python', 'tag:todo python', 'from:A.md', 'is:orphan',
                  'pithon --fuzzy' (fuzzy match to 'python').
       The index is RESTORED from data/index_snapshot.json by Kernel.initialize()
       (Stage 19), so a cold start is O(1) — no vault re-read.
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()  # restores graph + index from snapshot if present
    atexit.register(lambda: k.stop())
    engine = container.resolve("GraphQueryEngine")
    if getattr(args, "fuzzy", False):
        _dump(engine.fuzzy_search(args.query))
    else:
        _dump(engine.search(args.query))


def cmd_stop(args, container: Optional[object] = None) -> None:
    """No daemon runs between commands, so there is nothing to signal.

    We honor a pid-file convention for compatibility: if one exists we remove
    it; otherwise we report honestly that no per-command instance is running.
    """
    vault = args.vault or "."
    pid_path = os.path.join(vault, "kernel.pid")
    if os.path.exists(pid_path):
        try:
            os.remove(pid_path)
        except OSError:
            pass
        _dump({"stopped": True})
    else:
        _dump({"stopped": False,
               "reason": "no running daemon (Kernel runs per-command)"})


def cmd_repl(args, container) -> None:
    """Launch the interactive REPL (Stage 16).

    The Kernel is created ONCE, initialized + started, and handed to a
    ``KnowledgeOSRepl`` that drives it for the whole session. Every REPL
    command resolves services from the SAME container, so the kernel (and the
    shared graph) never gets rebuilt between commands. On REPL exit the kernel
    is stopped (which snapshots the graph) -- closing the Stage-13 limitation
    "no interactive REPL, only batch commands".
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()
    k.start()
    # Stage 19: the ContentIndex is restored from data/index_snapshot.json by
    # Kernel.initialize() (cold start is O(1), no vault re-read). The old
    # Stage-18 ensure_index() rebuild was removed.
    try:
        KnowledgeOSRepl(k, container).run()
    finally:
        # Guarantee shutdown even if the REPL loop propagates unexpectedly.
        k.stop()
