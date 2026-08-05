"""Stage 25 - Plugin System tests (10).

contracts.IPlugin (ABC port) + infrastructure.PluginLoader (filesystem
discovery: *.py with a top-level ``class Plugin``) + main.py wiring
(--plugin-dir pre-scan, subcommand merge, exporter merge into the DI
container, on_crawl_complete hook after batch crawl).

Real plugin files are written into tmp_path dirs; CLI-level behavior is
exercised through main.main(argv) in-process (fast) — the ad-hoc verifier
covers the true-subprocess path.
"""
from __future__ import annotations

import abc
import argparse
import json
import os
from pathlib import Path

import pytest

from contracts import IPlugin
from infrastructure import DependencyContainer, PluginLoader
import main as main_mod


GOOD_PLUGIN = '''
import json, os

def export_upper(graph):
    return "NODES=" + str(len(graph.get("nodes", [])))

class Plugin:
    def register_commands(self, sub):
        p = sub.add_parser("hello", help="demo")
        p.add_argument("--vault", default=None)
        p.set_defaults(func=lambda args, container: print(json.dumps({"plugin_ok": True})))

    def register_exporters(self, container):
        container.register_instance("export_upper", export_upper)

    def on_crawl_complete(self, graph):
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(str(len(graph.get("nodes", {}))))
'''


@pytest.fixture
def plugin_dir(tmp_path):
    d = tmp_path / "plugins"
    d.mkdir()
    (d / "good.py").write_text(GOOD_PLUGIN, encoding="utf-8")
    return str(d)


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "A.md").write_text("a [[B.md]]", encoding="utf-8")
    (v / "B.md").write_text("b", encoding="utf-8")
    return str(v)


# ----- contract -----
def test_iplugin_is_abstract_port():
    assert issubclass(IPlugin, abc.ABC)
    expected = {"register_commands", "register_exporters", "on_crawl_complete"}
    assert expected.issubset(IPlugin.__abstractmethods__)
    with pytest.raises(TypeError):
        IPlugin()


# ----- loader -----
def test_loader_discovers_plugin(plugin_dir):
    loader = PluginLoader(plugin_dir)
    plugins = loader.load()
    assert len(plugins) == 1
    assert loader.errors == []
    assert type(plugins[0]).__name__ == "Plugin"


def test_loader_missing_dir_is_safe(tmp_path):
    loader = PluginLoader(str(tmp_path / "does-not-exist"))
    assert loader.load() == []
    assert loader.errors == []


def test_loader_broken_plugin_fail_soft(plugin_dir):
    Path(plugin_dir, "broken.py").write_text(
        'raise RuntimeError("boom at import")', encoding="utf-8"
    )
    loader = PluginLoader(plugin_dir)
    plugins = loader.load()
    # good.py still loads; broken.py recorded, never raises.
    assert len(plugins) == 1
    assert len(loader.errors) == 1
    assert loader.errors[0][0] == "broken.py"
    assert "boom at import" in loader.errors[0][1]


def test_loader_file_without_plugin_class(plugin_dir):
    Path(plugin_dir, "noclass.py").write_text("X = 1\n", encoding="utf-8")
    loader = PluginLoader(plugin_dir)
    plugins = loader.load()
    assert len(plugins) == 1  # good.py only
    assert ("noclass.py", "no top-level 'class Plugin' found") in loader.errors


# ----- parser merge -----
def test_plugin_registers_subcommand(plugin_dir):
    loader = PluginLoader(plugin_dir)
    loader.load()
    from cli.parser import parse_args
    args = parse_args(["hello"], loader=loader)
    assert args.command == "hello"
    assert callable(args.func)


def test_plugin_duplicate_builtin_command_fail_soft(plugin_dir):
    # A plugin trying to redefine built-in 'crawl' must NOT take the CLI down.
    Path(plugin_dir, "clash.py").write_text(
        "class Plugin:\n"
        "    def register_commands(self, sub):\n"
        "        sub.add_parser('crawl')\n",
        encoding="utf-8",
    )
    loader = PluginLoader(plugin_dir)
    loader.load()
    from cli.parser import parse_args
    args = parse_args(["crawl", "--vault", "."], loader=loader)  # builtin wins
    assert args.command == "crawl"
    assert any("register_commands" in err for _, err in loader.errors)


# ----- exporter merge -----
def test_plugin_exporter_merged_into_container(plugin_dir):
    loader = PluginLoader(plugin_dir)
    loader.load()
    c = main_mod.build_container(".", loader=loader)
    assert c.has("export_upper")
    assert c.resolve("export_upper")({"nodes": [1, 2, 3]}) == "NODES=3"
    # Built-ins survive the merge.
    for fmt in ("dot", "json", "gexf"):
        assert c.has(f"export_{fmt}")


# ----- end-to-end via main.main -----
def test_crawl_fires_on_crawl_complete(plugin_dir, vault, capsys):
    main_mod.main(["--plugin-dir", plugin_dir, "crawl", "--vault", vault])
    hook = Path(plugin_dir, "hook.txt")
    assert hook.exists()
    assert hook.read_text(encoding="utf-8") == "2"  # A.md + B.md


def test_no_plugin_dir_zero_regression(vault, capsys):
    # Without --plugin-dir nothing changes: crawl works, no PluginLoader used.
    main_mod.main(["crawl", "--vault", vault])
    out = capsys.readouterr().out.strip().splitlines()[-1]
    stats = json.loads(out)
    assert stats["nodes"] == 2 and stats["edges"] == 1
    c = main_mod.build_container(vault)  # loader=None default
    assert c.resolve("PluginLoader") is None
