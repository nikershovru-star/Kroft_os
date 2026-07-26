"""Stage 13 - CLI unit tests (8)."""
import ast
import json
import os
from pathlib import Path

import pytest

import main


def test_cli_init_creates_directories(tmp_path):
    from cli import commands
    vault = tmp_path / "v_test"
    commands.cmd_init(type("A", (), {"vault": str(vault)})())
    assert vault.is_dir()
    assert (vault / "data").is_dir()


def test_cli_crawl_outputs_stats(tmp_path, capsys):
    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "A.md").write_text("#idea root links [[B]]", encoding="utf-8")
    (vault / "B.md").write_text("#todo leaf", encoding="utf-8")
    main.main(["crawl", "--vault", str(vault)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["files_scanned"] == 2
    assert data["nodes"] == 2


def test_cli_query_backlinks(tmp_path, capsys):
    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "A.md").write_text("hub [[B.md]] [[C.md]]", encoding="utf-8")
    (vault / "B.md").write_text("leaf", encoding="utf-8")
    (vault / "C.md").write_text("leaf", encoding="utf-8")
    main.main(["crawl", "--vault", str(vault)])
    capsys.readouterr()
    main.main(["query", "--vault", str(vault), "--backlinks", "B.md"])
    out = capsys.readouterr().out
    # BFS backlinks of B.md: A links to it
    assert json.loads(out) == ["A.md"]


def test_cli_status_shows_state(tmp_path, capsys):
    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "A.md").write_text("x", encoding="utf-8")
    main.main(["crawl", "--vault", str(vault)])
    capsys.readouterr()
    main.main(["status", "--vault", str(vault)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["state"] in ("INITIALIZED", "RUNNING")
    assert data["graph_nodes"] >= 1


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as e:
        main.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "init" in out and "crawl" in out


def test_cli_no_command(capsys):
    # No subcommand -> parser prints help and exits 2.
    with pytest.raises(SystemExit) as e:
        main.main([])
    assert e.value.code == 2


def test_cli_uses_di_container(tmp_path):
    # commands resolve ports/services through the container, never touch
    # adapters directly. We confirm the container built by main wires the
    # expected port names and that the crawler is a registered service.
    vault = tmp_path / "v"
    c = main.build_container(str(vault))
    for name in ("IFileSystem", "IEventBus", "IGraphBuilder",
                 "ICapabilityRegistry", "VaultStreamCrawler", "GraphQueryEngine"):
        assert c.has(name), f"container missing {name}"
    crawler = c.resolve("VaultStreamCrawler")
    engine = c.resolve("GraphQueryEngine")
    assert crawler.name() == "vault_stream_crawler"
    assert engine.name() == "graph_query_engine"


def test_cli_arch_no_adapters_import():
    src = (Path(__file__).resolve().parent.parent / "cli" / "commands.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "adapters":
                raise AssertionError("cli/commands.py imports adapters directly")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "adapters":
                    raise AssertionError("cli/commands.py imports adapters directly")
    assert True
