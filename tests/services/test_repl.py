"""Stage 16 - Interactive REPL tests (8).

Drives KROFT_OSRepl with an injectable line reader (a list of inputs)
so the loop runs without real stdin. The Kernel is created ONCE and handed
to the REPL, proving the kernel lives for the whole session (not rebuilt per
command).

Architecture contract asserted elsewhere (tests/test_architecture.py):
cli/repl.py imports kernel + services (+ contracts/infrastructure transitively)
but NEVER adapters.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from kernel import Kernel
from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from services import VaultStreamCrawler, GraphQueryEngine
from cli.repl import KROFT_OSRepl


def _make_vault(tmp_path: Path) -> str:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A.md").write_text("hub [[B.md]] [[C.md]]", encoding="utf-8")
    (vault / "B.md").write_text("leaf #todo", encoding="utf-8")
    (vault / "C.md").write_text("leaf #idea", encoding="utf-8")
    return str(vault)


def _build_container(vault: str) -> DependencyContainer:
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"),
            c.resolve("IEventBus"),
            c.resolve("IGraphBuilder"),
            vault,
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(c.resolve("IGraphBuilder")),
    )
    return c


def _repl_with(kernel, container, inputs):
    """Build a REPL whose reader yields `inputs` then ends via 'exit'."""
    it = iter(inputs)
    repl = KROFT_OSRepl(kernel, container, reader=lambda: next(it))
    return repl


# --------------------------------------------------------------------------
def test_repl_crawl_command(tmp_path, capsys):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    # Spy on crawl() through a fake crawler registration.
    called = {}

    class FakeCrawler:
        def name(self):
            return "fake_crawler"

        async def crawl(self):
            called["crawl"] = True
            return {"files_scanned": 3, "nodes": 3, "edges": 2}

    c.register_instance("VaultStreamCrawler", FakeCrawler())

    k = Kernel(c)
    k.initialize()
    k.start()
    _repl_with(k, c, ["crawl", "exit"]).run()
    assert called.get("crawl") is True
    out = capsys.readouterr().out
    assert json.loads(out)["nodes"] == 3
    assert k.state.name == "STOPPED"


def test_repl_query_backlinks(tmp_path, capsys):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    # Pre-build the graph (shared InMemoryGraphBuilder singleton).
    crawler = c.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())
    _repl_with(k, c, ["query backlinks C.md", "exit"]).run()
    out = capsys.readouterr().out
    assert json.loads(out) == ["A.md"]
    assert k.state.name == "STOPPED"


def test_repl_status(tmp_path, capsys):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    crawler = c.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())
    _repl_with(k, c, ["status", "exit"]).run()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["state"] == "RUNNING"
    assert data["graph_nodes"] >= 1
    assert "graph_edges" in data
    assert k.state.name == "STOPPED"


def test_repl_save(tmp_path):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    crawler = c.resolve("VaultStreamCrawler")
    asyncio.run(crawler.crawl())
    _repl_with(k, c, ["save", "exit"]).run()
    # save -> kernel.save() -> graph.snapshot() to data/graph_snapshot.json.
    snap = os.path.join(vault, "data", "graph_snapshot.json")
    assert os.path.exists(snap), "snapshot not written on save"
    assert k.state.name == "STOPPED"


def test_repl_help(tmp_path, capsys):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    _repl_with(k, c, ["help", "exit"]).run()
    out = capsys.readouterr().out
    assert "KROFT_OS v5 REPL" in out
    assert "crawl" in out
    assert "query" in out
    assert "backlinks" in out
    assert k.state.name == "STOPPED"


def test_repl_unknown_command(tmp_path, capsys):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()
    # 'foo' is unknown -> error line, session must NOT crash, then exit.
    _repl_with(k, c, ["foo", "exit"]).run()
    err = capsys.readouterr().err
    assert "unknown command" in err
    # Session survived and exited cleanly.
    assert k.state.name == "STOPPED"


def test_repl_keyboard_interrupt(tmp_path):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    k.initialize()
    k.start()

    def raising_reader():
        raise KeyboardInterrupt()

    repl = KROFT_OSRepl(k, c, reader=raising_reader)
    repl.run()  # Ctrl+C -> graceful save + stop
    assert k.state.name == "STOPPED"


def test_repl_kernel_lifecycle(tmp_path):
    vault = _make_vault(tmp_path)
    c = _build_container(vault)
    k = Kernel(c)
    # Count lifecycle transitions to prove the kernel is started ONCE,
    # survives the whole REPL session, and is stopped ONCE on exit.
    starts = {"n": 0}

    def counting_start(self=k):
        starts["n"] += 1
        Kernel.start(k)

    # Patch the bound method via a counting wrapper.
    original_start = k.start
    k.start = lambda: (starts.__setitem__("n", starts["n"] + 1), original_start())[1]
    k.initialize()
    k.start()
    assert k.state.name == "RUNNING"
    assert starts["n"] == 1
    _repl_with(k, c, ["status", "exit"]).run()
    # Still exactly one start -- the kernel was never rebuilt inside the REPL.
    assert starts["n"] == 1
    assert k.state.name == "STOPPED"
