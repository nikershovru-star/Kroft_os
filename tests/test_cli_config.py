"""Stage 15 - CLI <-> Config integration tests (4).

Verifies that:
  - `init` writes a knowledgeos.yaml template,
  - `crawl` reads autosave_interval from the config when CLI omits it,
  - CLI --autosave overrides the config value,
  - missing config falls back to the hardcoded default (60).
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KnowledgeOS-v5")

from kernel import Kernel
import cli.commands as commands
import main

PROJECT = r"C:\Users\Nita\Documents\Obsidian Vault\02-Projects\KnowledgeOS-v5" if False else \
    r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KnowledgeOS-v5"


def _capture_autosave(monkeypatch):
    captured = {}

    class SpyKernel(Kernel):
        def __init__(self, container=None, autosave_interval_sec=None, **kw):
            super().__init__(container, autosave_interval_sec=autosave_interval_sec, **kw)
            captured["autosave"] = autosave_interval_sec

    monkeypatch.setattr(commands, "Kernel", SpyKernel)
    return captured


def test_cmd_init_creates_config():
    vault = tempfile.mkdtemp(prefix="hermes-cli-cfg-")
    args = argparse.Namespace(vault=vault)
    commands.cmd_init(args)
    cfg_path = os.path.join(vault, "knowledgeos.yaml")
    assert os.path.exists(cfg_path), "init must create knowledgeos.yaml"
    content = open(cfg_path, encoding="utf-8").read()
    assert "autosave_interval" in content
    assert "vault:" in content
    assert "features:" in content


def test_crawl_uses_config_autosave(monkeypatch):
    vault = tempfile.mkdtemp(prefix="hermes-cli-cfg-")
    with open(os.path.join(vault, "knowledgeos.yaml"), "w", encoding="utf-8") as fh:
        fh.write("vault: .\nautosave_interval: 15\nfeatures:\n  extract_tags: true\n")
    container = main.build_container(vault)
    captured = _capture_autosave(monkeypatch)
    args = argparse.Namespace(vault=vault, autosave=None)
    commands.cmd_crawl(args, container)
    assert captured["autosave"] == 15.0, "crawl must read autosave_interval from config"


def test_cli_overrides_config(monkeypatch):
    vault = tempfile.mkdtemp(prefix="hermes-cli-cfg-")
    with open(os.path.join(vault, "knowledgeos.yaml"), "w", encoding="utf-8") as fh:
        fh.write("vault: .\nautosave_interval: 15\n")
    container = main.build_container(vault)
    captured = _capture_autosave(monkeypatch)
    args = argparse.Namespace(vault=vault, autosave=30.0)
    commands.cmd_crawl(args, container)
    assert captured["autosave"] == 30.0, "CLI --autosave must override config"


def test_missing_config_uses_defaults(monkeypatch):
    vault = tempfile.mkdtemp(prefix="hermes-cli-cfg-")
    # No knowledgeos.yaml present.
    container = main.build_container(vault)
    captured = _capture_autosave(monkeypatch)
    args = argparse.Namespace(vault=vault, autosave=None)
    commands.cmd_crawl(args, container)
    assert captured["autosave"] == 60.0, "missing config must fall back to default 60"
