"""Interactive REPL for KnowledgeOS v5 (Stage 16).

A long-running, line-oriented read-eval-print loop. The Kernel (and therefore
the whole DI container + services) is created ONCE by ``cmd_repl`` and stays
alive for the entire session -- it is NOT rebuilt per command (this closes the
Stage-13 honest limitation "no interactive REPL -- batch commands only").

Commands:
    crawl                          -> VaultStreamCrawler.crawl(); print stats
    query backlinks ID             -> GraphQueryEngine.backlinks(ID)  (JSON)
    query path FROM TO             -> GraphQueryEngine.path(FROM, TO) (JSON)
    query orphans                  -> GraphQueryEngine.orphan_nodes()  (JSON)
    query tags TAG                 -> GraphQueryEngine.nodes_by_tag(TAG) (JSON)
    status                         -> Kernel state + graph size (JSON)
    save                           -> force graph.snapshot() + GraphSnapshotted emit
    exit / quit                    -> graceful shutdown (snapshot + stop) + loop exit
    help                           -> list commands

Architecture contract:
    cli/ may import kernel, services, contracts, infrastructure. It must NOT
    import adapters directly -- all concrete ports are resolved through the
    container injected by cmd_repl. (Enforced by tests/test_architecture.py.)
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:  # keep runtime imports minimal + arch-clean
    from kernel import Kernel
    from infrastructure import DependencyContainer


# Prompt string shown before each read.
_PROMPT = "knowledgeos> "

# Known command verbs (for help + unknown-command feedback).
_COMMANDS = (
    ("crawl", "scan the vault and rebuild the knowledge graph"),
    ("query backlinks ID", "nodes that link TO <ID>"),
    ("query path FROM TO", "shortest path FROM -> TO (BFS)"),
    ("query orphans", "nodes with zero edges"),
    ("query tags TAG", "nodes carrying <TAG>"),
    ("search QUERY", "full-text AND-search over indexed .md content"),
    ("status", "show kernel state + graph size"),
    ("save", "force a graph snapshot (GraphSnapshotted)"),
    ("exit / quit", "graceful shutdown and leave the REPL"),
    ("help", "show this command list"),
)


def ensure_index(container, vault: str) -> None:
    """Rebuild the in-memory ContentIndex if it is empty (Stage 18).

    The index lives in RAM only (honest limitation), so a fresh process has
    an empty index even when the graph was restored from a snapshot AND the
    incremental tracker reports up_to_date (which skips scanning entirely --
    collision caught during Stage-18 integration). This helper re-reads all
    .md files via the container-resolved ports (no adapter imports) and
    indexes them, WITHOUT touching the graph or the crawl state file.
    """
    index = container.resolve("ContentIndex")
    if index.get_stats()["documents"] > 0:
        return
    fs = container.resolve("IFileSystem")
    tracker = container.resolve("CrawlStateTracker")
    for rel in tracker.scan_mtimes(vault):
        try:
            index.index_file(rel, fs.read_content(rel))
        except Exception:
            continue


class KnowledgeOSRepl:
    """Line-oriented REPL driving a single long-lived Kernel instance."""

    def __init__(
        self,
        kernel: "Kernel",
        container: "DependencyContainer",
        prompt: str = _PROMPT,
        reader: Optional[Callable[[], str]] = None,
    ) -> None:
        self._kernel = kernel
        self._container = container
        self._prompt = prompt
        # `reader` is injectable so tests can drive the loop without real stdin.
        self._reader = reader if reader is not None else self._default_read
        self._running = True
        self._history_enabled = False
        self._setup_readline()

    # ----- readline (optional) -----
    def _setup_readline(self) -> None:
        """Enable in-memory command history if readline is available.

        History is IN-MEMORY ONLY -- we never call read_history_file /
        write_history_file, so nothing is persisted across sessions.
        """
        try:  # pragma: no cover - platform dependent
            import readline  # noqa: F401  (importing enables arrow-key recall)
            self._history_enabled = True
        except ImportError:  # pragma: no cover - e.g. stock Windows python
            self._history_enabled = False

    def _default_read(self) -> str:
        return input(self._prompt)

    # ----- public loop -----
    def run(self) -> None:
        """Run the REPL until exit/quit or a graceful KeyboardInterrupt."""
        self._print_banner()
        while self._running:
            try:
                line = self._reader()
            except KeyboardInterrupt:
                # Ctrl+C at the prompt -> graceful save + stop + exit.
                self._handle_sigint()
                break
            try:
                self._dispatch(line)
            except KeyboardInterrupt:
                # Ctrl+C during a command (e.g. long crawl) -> same graceful exit.
                self._handle_sigint()
                break
            except Exception as exc:  # never let a bad command kill the session
                print(f"error: {exc}", file=sys.stderr)
        # Guarantee the kernel is stopped on every exit path.
        self._ensure_stopped()

    # ----- dispatch -----
    def _dispatch(self, raw: str) -> None:
        line = (raw or "").strip()
        if not line:
            return
        parts = line.split()
        verb = parts[0].lower()
        if verb in ("exit", "quit"):
            self._do_exit()
            return
        if verb == "help":
            self._do_help()
            return
        if verb == "crawl":
            self._do_crawl()
            return
        if verb == "status":
            self._do_status()
            return
        if verb == "save":
            self._do_save()
            return
        if verb == "query":
            self._do_query(parts[1:])
            return
        if verb == "search":
            self._do_search(parts[1:])
            return
        # Unknown command: report and continue (does NOT crash the session).
        print(
            f"unknown command: {verb!r} (type 'help' for the command list)",
            file=sys.stderr,
        )

    # ----- command implementations -----
    def _do_crawl(self) -> None:
        crawler = self._container.resolve("VaultStreamCrawler")
        stats = asyncio.run(crawler.crawl())
        print(json.dumps(stats, ensure_ascii=False))

    def _do_query(self, args: List[str]) -> None:
        if not args:
            print("query: missing subcommand (backlinks/path/orphans/tags)",
                  file=sys.stderr)
            return
        sub = args[0].lower()
        engine = self._container.resolve("GraphQueryEngine")
        if sub == "backlinks":
            if len(args) < 2:
                print("query backlinks: missing ID", file=sys.stderr)
                return
            result = engine.backlinks(args[1])
        elif sub == "path":
            if len(args) < 3:
                print("query path: missing FROM TO", file=sys.stderr)
                return
            result = engine.path(args[1], args[2])
        elif sub == "orphans":
            result = engine.orphan_nodes()
        elif sub == "tags":
            if len(args) < 2:
                print("query tags: missing TAG", file=sys.stderr)
                return
            result = engine.nodes_by_tag(args[1])
        else:
            print(f"query: unknown subcommand {sub!r}", file=sys.stderr)
            return
        print(json.dumps(result, ensure_ascii=False))

    def _do_status(self) -> None:
        graph = self._container.resolve("IGraphBuilder")
        g = graph.get_graph()
        print(json.dumps({
            "state": self._kernel.state.name,
            "graph_nodes": len(g["nodes"]),
            "graph_edges": len(g["edges"]),
        }, ensure_ascii=False))

    def _do_search(self, args: List[str]) -> None:
        """Full-text AND-search (Stage 18) via the shared ContentIndex."""
        if not args:
            print("search: missing QUERY", file=sys.stderr)
            return
        engine = self._container.resolve("GraphQueryEngine")
        print(json.dumps(engine.search(" ".join(args)), ensure_ascii=False))

    def _do_save(self) -> None:
        """Force a graph snapshot while the kernel keeps running."""
        self._kernel.save()

    def _do_help(self) -> None:
        print("KnowledgeOS v5 REPL -- commands:")
        for name, desc in _COMMANDS:
            print(f"  {name:<22} {desc}")

    def _do_exit(self) -> None:
        # exit/quit: graceful shutdown (Kernel.stop() also snapshots).
        self._graceful_shutdown()
        print("bye.", file=sys.stderr)

    # ----- graceful handling -----
    def _handle_sigint(self) -> None:
        print("\ninterrupted -- saving and stopping kernel.", file=sys.stderr)
        self._graceful_shutdown()

    def _graceful_shutdown(self) -> None:
        """Snapshot (best-effort) + stop the kernel. Idempotent."""
        try:
            self._kernel.save()
        except Exception:
            pass
        try:
            self._kernel.stop()
        except Exception:
            pass
        self._running = False

    def _ensure_stopped(self) -> None:
        if self._kernel.state.name != "STOPPED":
            try:
                self._kernel.stop()
            except Exception:
                pass

    def _print_banner(self) -> None:
        print(
            "KnowledgeOS v5 interactive REPL. Type 'help' for commands, "
            "'exit' to quit.",
            file=sys.stderr,
        )
