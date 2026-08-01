"""KROFT_OS v5 entrypoint.

Entrypoint only — delegates ALL wiring to the Composition Root (composition/).
Run: `python main.py <command>`. See ADR-026 (Composition Root) + ADR-029.
"""
from __future__ import annotations

import os as _os
import sys as _sys

from composition import build_container
from infrastructure import PluginLoader

from cli.parser import parse_args
from cli.commands import (
    cmd_init, cmd_crawl, cmd_query, cmd_status, cmd_stop, cmd_repl, cmd_search, cmd_export, cmd_watch, cmd_serve, cmd_semantic, cmd_hybrid, cmd_desktop, cmd_agent, cmd_schedule,
)


def _prescan_plugin_dir(argv) -> str | None:
    """Extract --plugin-dir from anywhere in argv (Stage 25)."""
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
                argv.pop(i); argv.pop(i)
        except ValueError:
            pass
    return known.plugin_dir


def _prescan_desktop_adapter(argv) -> str:
    """Extract --desktop-adapter from anywhere in argv (Stage 36)."""
    import argparse as _argparse
    pre = _argparse.ArgumentParser(add_help=False)
    pre.add_argument("--desktop-adapter", dest="desktop_adapter", default=None)
    known, _ = pre.parse_known_args(argv)
    if known.desktop_adapter is not None:
        try:
            i = argv.index("--desktop-adapter")
            if "=" in argv[i]:
                argv.pop(i)
            else:
                argv.pop(i); argv.pop(i)
        except (ValueError, IndexError):
            pass
    if known.desktop_adapter in ("mock", "pyautogui"):
        return known.desktop_adapter
    env = _os.environ.get("DESKTOP_ADAPTER")
    if env in ("mock", "pyautogui"):
        return env
    return "mock"


def main(argv=None) -> None:
    if argv is None:
        argv = _sys.argv[1:]
    else:
        argv = list(argv)
    plugin_dir = _prescan_plugin_dir(argv)
    desktop_adapter = _prescan_desktop_adapter(argv)
    loader = None
    if plugin_dir is not None:
        loader = PluginLoader(plugin_dir)
        loader.load()
        for fname, err in loader.errors:
            print(f"[plugin] {fname}: {err}", file=_sys.stderr)
    args = parse_args(argv, loader=loader)
    build = lambda: build_container(args.vault, loader=loader, desktop_adapter=desktop_adapter)
    if getattr(args, "func", None) is not None and args.command not in _BUILTIN_COMMANDS:
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
