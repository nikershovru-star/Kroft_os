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
    search QUERY                   -> full-text AND-search + DSL filters (JSON)
    fuzzy QUERY                   -> fuzzy full-text search (e.g. 'fuzzy pithon')
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
    ("search QUERY", "full-text AND-search + DSL filters (tag:X, from:X, to:X, is:orphan)"),
    ("semantic QUERY", "semantic vector search (top-10 by default)"),
    ("hybrid QUERY", "hybrid lexical+semantic RRF search (top-10 by default)"),
    ("desktop ACTION", "desktop automation: click x y | type text | screenshot | cursor | open app"),
    ("desktop open_note QUERY", "search+open top note in default app"),
    ("agent COMMAND", "Hermes agent: find/open/show/export (try 'agent find python')"),
    ("agent --dry-run COMMAND", "show execution plan without running"),
    ("schedule add [--cron EXPR] CMD", "schedule a command (every N / daily HH:MM)"),
    ("schedule list", "show scheduled jobs"),
    ("schedule cancel ID", "cancel a job"),
    ("schedule start", "start the scheduler daemon"),
    ("schedule stop", "stop the scheduler daemon"),
    ("desktop list_notes QUERY", "list top-k note candidates from hybrid search"),
    ("export FORMAT [OUTPUT]", "export graph to dot/json/gexf (FORMAT in dot/json/gexf; OUTPUT file or '-' stdout)"),
    ("watch [--interval N]", "start auto-recrawl on .md change (background thread; stop with 'watch stop')"),
    ("serve [PORT]", "start HTTP server for the web UI (default 8080; --auth via CLI only)"),
    ("status", "show kernel state + graph size"),
    ("save", "force a graph snapshot (GraphSnapshotted)"),
    ("exit / quit", "graceful shutdown and leave the REPL"),
    ("help", "show this command list"),
)


def ensure_index(container, vault: str) -> None:  # pragma: no cover - legacy no-op
    """REMOVED in Stage 19 (`feat(v5): Этап 19 — Index Persistence`).

    The ContentIndex is now restored from `data/index_snapshot.json` by
    ``Kernel.initialize()``, so a cold CLI/REPL start is O(1) (no vault re-read).
    Retained as a private, no-op stub for one release so external callers that
    referenced it survive; it does nothing.
    """
    return None


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
        """Enable in-memory command history + Tab autocomplete if readline is
        available.

        History is IN-MEMORY ONLY -- we never call read_history_file /
        write_history_file, so nothing is persisted across sessions.

        Stage 20: Tab autocomplete via readline.set_completer. Completes
        command verbs at the start of the line, and indexed terms after
        ``search``/``fuzzy``. The completer resolves ``ContentIndex`` from
        the DI container (never importing the sibling service directly).
        """
        try:  # pragma: no cover - platform dependent
            import readline  # noqa: F401  (importing enables arrow-key recall)
            readline.set_completer(self._completer)
            readline.parse_and_bind("tab: complete")
            self._history_enabled = True
        except ImportError:  # pragma: no cover - e.g. stock Windows python
            self._history_enabled = False

    def _completer(self, text: str, state: int):
        """readline completer: commands, or indexed terms (after search/fuzzy).

        Caches candidates for a given line in ``self._matches`` (readline calls
        this repeatedly with state=0,1,2... until it returns None).
        """
        if state == 0:
            try:
                line = readline.get_line_buffer()  # type: ignore[name-defined]
            except Exception:
                line = ""
            parts = line.strip().split()
            if len(parts) >= 1 and parts[0] in ("search", "fuzzy"):
                # Complete indexed terms by the last token prefix.
                prefix = parts[-1] if len(parts) >= 2 else ""
                try:
                    index = self._container.resolve("ContentIndex")
                    self._matches = index.suggest(prefix, limit=20) if index else []
                except Exception:
                    self._matches = []
            else:
                # Complete command verbs.
                cmds = [
                    "crawl", "query", "search", "fuzzy", "status",
                    "save", "exit", "quit", "help", "watch", "serve",
                ]
                self._matches = [c for c in cmds if c.startswith(text)]
        try:
            return self._matches[state]
        except (IndexError, AttributeError):
            return None

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
        if verb == "fuzzy":
            self._do_fuzzy(parts[1:])
            return
        if verb == "semantic":
            self._do_semantic(parts[1:])
            return
        if verb == "hybrid":
            self._do_hybrid(parts[1:])
            return
        if verb == "desktop":
            self._do_desktop(parts[1:])
            return
        if verb == "agent":
            self._do_agent(parts[1:])
            return
        if verb == "schedule":
            self._do_schedule(parts[1:])
            return
        if verb == "export":
            self._do_export(parts[1:])
            return
        if verb == "watch":
            self._do_watch(parts[1:])
            return
        if verb == "serve":
            self._do_serve(parts[1:])
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
        """Full-text AND-search (Stage 18/21) via the shared ContentIndex."""
        if not args:
            print("search: missing QUERY", file=sys.stderr)
            return
        engine = self._container.resolve("GraphQueryEngine")
        print(json.dumps(engine.search(" ".join(args)), ensure_ascii=False))

    def _do_fuzzy(self, args: List[str]) -> None:
        """Fuzzy full-text search (Stage 20) via ContentIndex.fuzzy_search."""
        if not args:
            print("fuzzy: missing QUERY", file=sys.stderr)
            return
        engine = self._container.resolve("GraphQueryEngine")
        print(json.dumps(engine.fuzzy_search(" ".join(args)), ensure_ascii=False))

    def _do_semantic(self, args: List[str]) -> None:
        """Semantic vector search (Stage 29) via SemanticIndex."""
        if not args:
            print("semantic: missing QUERY", file=sys.stderr)
            return
        top_k = 10
        if len(args) >= 3 and args[-2] == "--top-k":
            try:
                top_k = int(args[-1])
                args = args[:-2]
            except ValueError:
                pass
        engine = self._container.resolve("GraphQueryEngine")
        print(json.dumps(engine.semantic_search(" ".join(args), top_k=top_k), ensure_ascii=False))

    def _do_hybrid(self, args: List[str]) -> None:
        """Hybrid lexical+semantic RRF search (Stage 30) via hybrid_search."""
        if not args:
            print("hybrid: missing QUERY", file=sys.stderr)
            return
        top_k = 10
        if len(args) >= 3 and args[-2] == "--top-k":
            try:
                top_k = int(args[-1])
                args = args[:-2]
            except ValueError:
                pass
        engine = self._container.resolve("GraphQueryEngine")
        print(json.dumps(engine.hybrid_search(" ".join(args), top_k=top_k), ensure_ascii=False))

    def _do_desktop(self, args: List[str]) -> None:
        """Desktop automation (Stage 31)."""
        if not args:
            print("desktop: missing ACTION", file=sys.stderr)
            return
        action = args[0]
        ds = self._container.resolve("DesktopService")
        if action == "click":
            if len(args) != 3:
                print("desktop click: need X Y", file=sys.stderr)
                return
            ds.click_at(int(args[1]), int(args[2]))
            print(json.dumps({"ok": True, "action": "click"}))
        elif action == "type":
            if len(args) < 2:
                print("desktop type: need TEXT", file=sys.stderr)
                return
            ds.type_text(" ".join(args[1:]))
            print(json.dumps({"ok": True, "action": "type"}))
        elif action == "screenshot":
            data = ds.capture_screen()
            import base64
            print(json.dumps({"ok": True, "action": "screenshot", "size": len(data)}))
        elif action == "cursor":
            x, y = ds.where_is_cursor()
            print(json.dumps({"ok": True, "action": "cursor", "x": x, "y": y}))
        elif action == "open":
            if len(args) < 2:
                print("desktop open: need APP_NAME", file=sys.stderr)
                return
            ds.launch(args[1])
            print(json.dumps({"ok": True, "action": "open"}))
        elif action == "open_note":
            if len(args) < 2:
                print("desktop open_note: need QUERY", file=sys.stderr)
                return
            top_k = 1
            if len(args) >= 4 and args[-2] == "--top-k":
                try:
                    top_k = int(args[-1])
                    args = args[:-2]
                except ValueError:
                    pass
            orch = self._container.resolve("DesktopOrchestrator")
            result = orch.open_note(" ".join(args[1:]), top_k=top_k)
            print(json.dumps(result, ensure_ascii=False))
        elif action == "list_notes":
            if len(args) < 2:
                print("desktop list_notes: need QUERY", file=sys.stderr)
                return
            top_k = 5
            if len(args) >= 4 and args[-2] == "--top-k":
                try:
                    top_k = int(args[-1])
                    args = args[:-2]
                except ValueError:
                    pass
            orch = self._container.resolve("DesktopOrchestrator")
            result = orch.list_notes(" ".join(args[1:]), top_k=top_k)
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"desktop: unknown action {action}", file=sys.stderr)

    def _do_agent(self, args: List[str]) -> None:
        """Hermes agent: natural language command execution (Stage 33)."""
        if not args:
            print("agent: missing COMMAND", file=sys.stderr)
            return
        dry_run = False
        if args[0] == "--dry-run":
            dry_run = True
            args = args[1:]
        if not args:
            print("agent: missing COMMAND after --dry-run", file=sys.stderr)
            return
        command = " ".join(args)
        agent = self._container.resolve("IAgent")
        if dry_run:
            plan = agent._svc.plan(command)  # type: ignore[attr-defined]
            print(json.dumps({"dry_run": True, "plan": plan}, ensure_ascii=False))
        else:
            result = agent.execute(command)
            print(json.dumps(result, ensure_ascii=False))

    def _do_schedule(self, args: List[str]) -> None:
        if not args:
            print("schedule: need ACTION", file=sys.stderr)
            return
        sched: SchedulerService = self._container.resolve("SchedulerService")
        action = args[0]
        if action == "add":
            cron = "every 60"
            cmd_start = 1
            if len(args) >= 3 and args[1] == "--cron":
                cron = args[2]
                cmd_start = 3
            command = " ".join(args[cmd_start:])
            if not command:
                print("schedule add: need COMMAND", file=sys.stderr)
                return
            jid = sched.add(cron, command)
            print(json.dumps({"ok": True, "id": jid}))
        elif action == "list":
            print(json.dumps(sched.list_jobs(), ensure_ascii=False))
        elif action == "cancel" and len(args) == 2:
            print(json.dumps({"ok": sched.cancel(args[1])}))
        elif action == "start":
            sched.start()
            print(json.dumps({"ok": True, "status": "started"}))
        elif action == "stop":
            sched.stop()
            print(json.dumps({"ok": True, "status": "stopped"}))
        else:
            print(f"schedule: unknown action {action}", file=sys.stderr)

    def _do_export(self, args: List[str]) -> None:
        """Export the live graph to dot/json/gexf (Stage 23).

        `export FORMAT [OUTPUT]` — FORMAT in {dot, json, gexf}; OUTPUT is a
        file path, or '-' / omitted for stdout. The exporter is resolved from
        the DI container by name (cli/ must not import adapters directly).
        """
        if not args:
            print("export: missing FORMAT (dot|json|gexf)", file=sys.stderr)
            return
        fmt = args[0].lower()
        if fmt not in ("dot", "json", "gexf"):
            print(f"export: unknown format {fmt!r} (use dot|json|gexf)",
                  file=sys.stderr)
            return
        output = args[1] if len(args) >= 2 else "-"
        engine = self._container.resolve("GraphQueryEngine")
        graph = engine._snapshot()
        exporter = self._container.resolve(f"export_{fmt}")
        data = exporter(graph)
        if output == "-":
            print(data)
        else:
            self._container.resolve("IFileSystem").write_content(output, data)

    def _do_watch(self, args: List[str]) -> None:
        """Start the WatchService in a background thread (REPL stays live).

        Honors `watch stop` to halt it. Uses the DI-resolved WatchService +
        FileWatcher (cli/ never imports adapters directly). The watch runs in
        its own daemon thread so the REPL loop keeps accepting commands.
        """
        if args and args[0] in ("stop", "off"):
            ws = getattr(self, "_repl_watch", None)
            if ws is not None:
                ws.stop()
                self._repl_watch = None
                print("watch stopped", file=sys.stderr)
            else:
                print("watch: not running", file=sys.stderr)
            return
        if getattr(self, "_repl_watch", None) is not None:
            print("watch: already running (use 'watch stop')", file=sys.stderr)
            return
        ws = self._container.resolve("WatchService")
        ws.start()
        self._repl_watch = ws
        backend = "watchdog" if getattr(self._container.resolve("FileWatcher"), "using_watchdog", False) else "polling"
        print(f"watch started ({backend} backend); 'watch stop' to halt", file=sys.stderr)

    def _do_serve(self, args: List[str]) -> None:
        """Start the HTTP server (Stage 22) in a background thread.

        Resolves ``KnowledgeOSServer`` from the DI container by name (cli/
        never imports adapters directly). The REPL loop keeps running, so
        'stop' / 'exit' leaves the REPL -- it does NOT shut the server down.
        """
        if args:
            try:
                port = int(args[0])
            except ValueError:
                print(f"serve: invalid port {args[0]!r}", file=sys.stderr)
                return
        else:
            port = 8080
        server = self._container.resolve("KnowledgeOSServer")
        server._port = port
        server.start()
        print(
            f"Server running at http://127.0.0.1:{server.port}/",
            file=sys.stderr,
        )
        print(
            "Note: runs in a background thread. 'stop'/'exit' shuts down the "
            "REPL, not the server.",
            file=sys.stderr,
        )

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
