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
import sys
from pathlib import Path
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
    # Stage 25: fire plugin crawl hooks (duck-typed loader from the container;
    # None when no --plugin-dir was given -- zero-regression path).
    loader = container.resolve("PluginLoader") if container.has("PluginLoader") else None
    if loader is not None:
        loader.notify_crawl_complete(container.resolve("IGraphBuilder").get_graph())
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


def cmd_semantic(args, container) -> None:
    """Semantic vector search (Stage 29).

    Uses the wired SemanticIndex + IEmbedding (default MockEmbeddingAdapter).
    Restored from data/semantic_snapshot.json by Kernel.initialize() (Stage 29),
    so a cold start is O(1) — no vault re-read.
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()  # restores graph + index + semantic from snapshot if present
    atexit.register(lambda: k.stop())
    engine = container.resolve("GraphQueryEngine")
    query = " ".join(args.query) if isinstance(args.query, list) else args.query
    _dump(engine.semantic_search(query, top_k=args.top_k))


def cmd_hybrid(args, container) -> None:
    """Hybrid lexical+semantic search (Stage 30).

    RRF-fused result via GraphQueryEngine.hybrid_search — combines the
    ContentIndex (lexical) and SemanticIndex (semantic) rank lists. Zero
    regression: if either engine is unwired the fusion degrades to the other.
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()  # restores graph + index + semantic from snapshot if present
    atexit.register(lambda: k.stop())
    engine = container.resolve("GraphQueryEngine")
    query = " ".join(args.query) if isinstance(args.query, list) else args.query
    _dump(engine.hybrid_search(query, top_k=args.top_k))


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


def cmd_watch(args, container) -> None:
    """Watch the vault and auto-recrawl on every ``.md`` change (Stage 27).

    Builds + initializes a Kernel (restores graph/index from snapshot), then
    starts the WatchService. The WatchService resolves the FileWatcher (an
    adapter) from the DI container -- cli/ never imports adapters directly
    (arch gate). Runs until KeyboardInterrupt, then stops the watcher and
    kernel.
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()
    k.start()
    watch = container.resolve("WatchService")
    # Inject the live Kernel so each recrawl persists a snapshot (duck-typed;
    # WatchService never imports kernel). CLI --interval / --no-watchdog
    # override the FileWatcher defaults.
    watch._kernel = k
    watcher = container.resolve("FileWatcher")
    try:
        watcher._interval = max(0.05, float(args.interval))
    except (AttributeError, TypeError, ValueError):
        pass
    if getattr(args, "no_watchdog", False):
        watcher._use_watchdog = False
    atexit.register(lambda: _safe_stop_watch(watch, k))
    try:
        print("watching... (Ctrl+C to stop)", file=sys.stderr)
        watch.watch()
    except KeyboardInterrupt:
        pass
    finally:
        watch.stop()
        k.stop()


def _safe_stop_watch(watch, k) -> None:
    try:
        watch.stop()
    except Exception:
        pass
    try:
        k.stop()
    except Exception:
        pass


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


def cmd_export(args, container) -> None:
    """Export the live graph to dot/json/gexf (Stage 23).

    The exporter functions live in ``adapters/exporters/`` -- the ONLY place
    that touches external serialization formats. cli/ must NOT import adapters
    directly (arch gate), so the exporter is resolved from the DI container by
    name (registered in main.build_container, the composition root).

    Output resolution:
      * ``--output -``          -> print to stdout.
      * relative / vault-absolute path -> written via the IFileSystem port
        (confined to the vault, same as every other file op).
      * absolute path OUTSIDE the vault -> written directly with open() (an
        honest limitation: exporting out of the vault bypasses the FS adapter).
    """
    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    # Restore the graph (and index) from data/graph_snapshot.json if a prior
    # crawl persisted one -- without this the in-memory IGraphBuilder is empty
    # and export would emit a 0-node graph. Mirrors cmd_query/cmd_search.
    k.initialize()
    atexit.register(lambda: k.stop())
    engine = container.resolve("GraphQueryEngine")
    graph = engine._snapshot()  # existing method on GraphQueryEngine
    # Stage 25: --format is no longer constrained by argparse choices --
    # plugins may register new exporters (export_<fmt>) in the container.
    # Unknown format -> graceful JSON error + exit 2 (not a KeyError traceback).
    if not container.has(f"export_{args.format}"):
        _dump({"error": f"unknown export format '{args.format}'",
               "known": sorted(n[len("export_"):] for n in container.names()
                               if n.startswith("export_"))})
        sys.exit(2)
    exporter = container.resolve(f"export_{args.format}")
    data = exporter(graph)

    if args.output == "-":
        print(data)
        return

    output = args.output
    fs = container.resolve("IFileSystem")
    base = getattr(fs, "_base", None)
    # Decide whether the output lives inside the vault (FS-adapter-safe).
    is_outside = False
    if base is not None and os.path.isabs(output):
        try:
            fs._safe(output)  # raises ValueError if it escapes the vault
        except (ValueError, Exception):
            is_outside = True
    if is_outside:
        # Honest path: export to an absolute location outside the vault.
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(data, encoding="utf-8")
    else:
        fs.write_content(output, data)


def cmd_serve(args, container) -> None:
    """Start the HTTP server for the web UI (Stage 22).

    Builds a Kernel (restores graph/index from snapshot), starts it, then
    resolves the ``KnowledgeOSServer`` adapter from the DI container (cli/
    must NOT import adapters directly -- arch gate) and runs its serve_forever
    loop on a daemon thread while the main thread sleeps until Ctrl+C.

    Overrides the server's host/port from --host/--port before start() so the
    CLI controls binding without touching the adapter's constructor in cli/.
    """
    import time

    effective = _resolve_config(args, container)
    k = Kernel(container, autosave_interval_sec=effective["autosave_interval"])
    k.initialize()
    k.start()
    atexit.register(lambda: k.stop())

    server = container.resolve("KnowledgeOSServer")
    # Stage 28: optional basic auth. Registered into DI here (composition
    # concern) — the adapter resolves "AuthService" per-request; without
    # --auth nothing is registered and the server behaves exactly as Stage 22.
    if getattr(args, "auth", None):
        if ":" not in args.auth:
            print('serve: --auth must be "user:pass"', file=sys.stderr)
            raise SystemExit(2)
        user, passwd = args.auth.split(":", 1)
        from services import SimpleAuthService  # cli -> services (axis-clean)
        container.register_instance("AuthService", SimpleAuthService(user, passwd))
    server._host = args.host
    server._port = args.port
    server.start()
    print(f"Server running at http://{server._host}:{server.port}/", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("Server stopped.", file=sys.stderr)
