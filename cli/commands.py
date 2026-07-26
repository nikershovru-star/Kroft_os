"""CLI command implementations.

Each command owns its Kernel lifecycle: build (or receive) a DI container,
drive Kernel init -> start -> stop, print a JSON result to stdout. There is NO
long-running daemon -- every invocation spins the Kernel up and tears it down.
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import Optional

from kernel import Kernel
from services import VaultStreamCrawler, GraphQueryEngine


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def cmd_init(args, container: Optional[object] = None) -> None:
    """Create <vault>/ and <vault>/data/ so the snapshot has a home."""
    os.makedirs(args.vault, exist_ok=True)
    data_dir = os.path.join(args.vault, "data")
    os.makedirs(data_dir, exist_ok=True)
    _dump({"created": [args.vault, data_dir]})


def cmd_crawl(args, container) -> None:
    k = Kernel(container)
    k.initialize()
    k.start()
    crawler = container.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())
    k.stop()  # persists snapshot before teardown
    _dump(crawler.get_stats())


def cmd_query(args, container) -> None:
    k = Kernel(container)
    k.initialize()  # restores graph from snapshot if present
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
    k = Kernel(container)
    k.initialize()  # restores graph from snapshot if present
    graph = container.resolve("IGraphBuilder")
    _dump({
        "state": k.state.name,
        "graph_nodes": len(graph.get_graph()["nodes"]),
        "graph_edges": len(graph.get_graph()["edges"]),
    })


def cmd_stop(args, container: Optional[object] = None) -> None:
    """No daemon runs between commands, so there is nothing to signal.

    We honor a pid-file convention for compatibility: if one exists we remove
    it; otherwise we report honestly that no per-command instance is running.
    """
    pid_path = os.path.join(args.vault, "kernel.pid")
    if os.path.exists(pid_path):
        try:
            os.remove(pid_path)
        except OSError:
            pass
        _dump({"stopped": True})
    else:
        _dump({"stopped": False,
               "reason": "no running daemon (Kernel runs per-command)"})
