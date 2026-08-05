"""Stage 13 - CLI E2E tests (4).

NOTE ON NODE-IDS: with LocalFileSystemAdapter(base=vault_path), list_dir()
returns entries RELATIVE TO THE VAULT ROOT (e.g. "A.md", "sub/B.md"). The
crawler therefore uses vault-root-relative node-ids, and wiki-links inside
notes resolve relative to the vault root. Hence every query here uses bare
ids ("A.md", "C.md") -- NOT "v/A.md". This matches the unit tests in
test_cli.py and the real adapter semantics.
"""
import json
from pathlib import Path

import main


def _seed(vault):
    vault.mkdir(exist_ok=True)
    (vault / "A.md").write_text("hub links [[B.md]] and [[C.md]]", encoding="utf-8")
    (vault / "B.md").write_text("leaf #todo", encoding="utf-8")
    (vault / "C.md").write_text("leaf #idea", encoding="utf-8")


def test_full_cli_workflow(tmp_path, capsys):
    vault = tmp_path / "v"
    # init
    main.main(["init", "--vault", str(vault)])
    assert json.loads(capsys.readouterr().out)["created"]
    # crawl
    _seed(vault)
    main.main(["crawl", "--vault", str(vault)])
    stats = json.loads(capsys.readouterr().out)
    assert stats["files_scanned"] == 3
    # query backlinks (node-ids are vault-root-relative)
    main.main(["query", "--vault", str(vault), "--backlinks", "C.md"])
    assert json.loads(capsys.readouterr().out) == ["A.md"]
    # query path
    main.main(["query", "--vault", str(vault), "--path", "A.md", "C.md"])
    assert json.loads(capsys.readouterr().out) == ["A.md", "C.md"]
    # status
    main.main(["status", "--vault", str(vault)])
    st = json.loads(capsys.readouterr().out)
    assert st["graph_nodes"] == 3
    # stop (no daemon -> honest no-op)
    main.main(["stop", "--vault", str(vault)])
    assert json.loads(capsys.readouterr().out)["stopped"] in (True, False)


def test_cli_persistence(tmp_path, capsys):
    vault = tmp_path / "v"
    _seed(vault)
    # First "process": crawl persists snapshot
    main.main(["crawl", "--vault", str(vault)])
    capsys.readouterr()
    # Second "process": status restores from snapshot without re-crawling
    main.main(["status", "--vault", str(vault)])
    st = json.loads(capsys.readouterr().out)
    assert st["graph_nodes"] == 3
    # query works on the restored graph (no crawl between)
    main.main(["query", "--vault", str(vault), "--backlinks", "C.md"])
    assert json.loads(capsys.readouterr().out) == ["A.md"]


def test_cli_empty_vault(tmp_path, capsys):
    vault = tmp_path / "v"
    vault.mkdir()
    main.main(["crawl", "--vault", str(vault)])
    stats = json.loads(capsys.readouterr().out)
    assert stats["files_scanned"] == 0
    assert stats["nodes"] == 0
    # status on empty vault still works
    main.main(["status", "--vault", str(vault)])
    st = json.loads(capsys.readouterr().out)
    assert st["graph_nodes"] == 0


def test_cli_query_without_crawl(tmp_path, capsys):
    vault = tmp_path / "v"
    vault.mkdir()
    # query on a fresh (empty) graph -> empty result, no crash
    main.main(["query", "--vault", str(vault), "--orphans"])
    assert json.loads(capsys.readouterr().out) == []
    main.main(["query", "--vault", str(vault), "--backlinks", "X.md"])
    assert json.loads(capsys.readouterr().out) == []
    main.main(["query", "--vault", str(vault), "--path", "A.md", "B.md"])
    assert json.loads(capsys.readouterr().out) is None
