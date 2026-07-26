"""CLI argument parser (argparse) for KnowledgeOS v5."""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="KnowledgeOS v5 -- knowledge operating system CLI",
    )
    sub = p.add_subparsers(dest="command")

    pi = sub.add_parser("init", help="Create data/ and vault/ directory structure")
    pi.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")

    pc = sub.add_parser("crawl", help="Crawl a Vault and build the knowledge graph")
    pc.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")
    pc.add_argument("--autosave", type=float, default=None,
                    help="Graph autosave interval in seconds (default 60; 0 disables; "
                         "overrides knowledgeos.yaml)")

    pq = sub.add_parser("query", help="Query the knowledge graph")
    pq.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")
    pq.add_argument("--backlinks", metavar="ID", help="Nodes that link TO <ID>")
    pq.add_argument("--path", nargs=2, metavar=("FROM", "TO"),
                    help="Shortest path FROM -> TO (BFS)")
    pq.add_argument("--orphans", action="store_true", help="Orphan nodes (zero-degree)")
    pq.add_argument("--tags", metavar="TAG", help="Nodes carrying <TAG>")

    pse = sub.add_parser(
        "search",
        help="Full-text + structural search over indexed .md (Stage 21 DSL, Stage 20 --fuzzy)",
    )
    pse.add_argument(
        "query",
        help="Search query (Stage 21 DSL): 'python' | 'tag:todo python' | "
             "'from:A.md' | 'to:A.md' | 'is:orphan' — text ANDed with filters",
    )
    pse.add_argument(
        "--fuzzy",
        action="store_true",
        help="Fuzzy token matching (e.g. 'pithon' matches 'python') via difflib",
    )
    pse.add_argument(
        "--vault", default=None,
        help="Path to the vault directory (or read from knowledgeos.yaml)",
    )

    ps = sub.add_parser("status", help="Show kernel state and graph size")
    ps.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")
    ps.add_argument("--autosave", type=float, default=None,
                    help="Graph autosave interval in seconds (default 60; 0 disables; "
                         "overrides knowledgeos.yaml)")

    pst = sub.add_parser("stop", help="Graceful shutdown (pid-file only; no daemon)")
    pst.add_argument("--vault", default=None,
                     help="Path to the vault directory (or read from knowledgeos.yaml)")

    pr = sub.add_parser("repl", help="Interactive REPL (kernel lives for the session)")
    pr.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")

    pex = sub.add_parser("export", help="Export graph to dot/json/gexf (Stage 23)")
    pex.add_argument("--format", choices=["dot", "json", "gexf"], default="json",
                     help="Export format (default: json)")
    pex.add_argument("--output", default="-",
                     help="Output file path ('-' for stdout)")
    pex.add_argument("--vault", default=None,
                     help="Path to the vault directory (or read from knowledgeos.yaml)")

    pw = sub.add_parser("watch", help="Watch a vault and auto-recrawl on .md change (Stage 27)")
    pw.add_argument("--vault", default=None,
                    help="Path to the vault directory (or read from knowledgeos.yaml)")
    pw.add_argument("--interval", type=float, default=2.0,
                    help="Polling interval in seconds (default 2.0; ignored if watchdog active)")
    pw.add_argument("--no-watchdog", action="store_true",
                    help="Force polling fallback even if watchdog is installed")

    return p


def parse_args(argv=None) -> argparse.Namespace:
    p = build_parser()
    args = p.parse_args(argv)
    if args.command is None:
        p.print_help()
        sys.exit(2)
    return args
