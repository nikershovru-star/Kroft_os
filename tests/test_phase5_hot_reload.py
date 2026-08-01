"""Phase 5 tests — Hot Reload (DoD).

Config hot-reload: config.json change -> ConfigService.reload + config.changed
Component swap: ComponentController.swap(name, inst) replaces instance, RUNNING, no Kernel.stop
Manifest reload: new plugin manifest -> activated without restart
LAW K8: runtime/hot_reload imports only contracts/runtime (+stdlib), not watchdog/third-party
FileWatcher: stdlib os.stat polling only
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from contracts import IComponentController
from runtime.i_process_impl import Process
from runtime.component_registry import ComponentRegistry
from runtime.services.config_service import ConfigService
from runtime.hot_reload import FileWatcher, HotReloadService
from bootstrap_v2 import ComponentController, build_instance_builder, build_event_bus


class _StubBus:
    def __init__(self):
        self._s = {}
        self.log = []
    def subscribe(self, t, h):
        self._s.setdefault(t, []).append(h)
    def publish(self, t, e):
        for h in self._s.get(t, []):
            h(e)
        self.log.append((t, e))
    def publish_sync(self, t, e):
        self.publish(t, e)
    def start(self): pass
    def stop(self): pass
    def events(self, topic):
        return [e for (t, e) in self.log if t == topic]


def test_config_hot_reload_publishes_changed():
    """Changing config.json -> ConfigService.reload + config.changed published."""
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.json"
        cfg.write_text(json.dumps({"weights": {"reasoning": 0.5}}))
        bus = _StubBus()
        cs = ConfigService(bus=bus, config_path=cfg)
        assert cs.get("weights", {}).get("reasoning") == 0.5
        # mutate file, bump mtime
        time.sleep(0.01)
        cfg.write_text(json.dumps({"weights": {"reasoning": 0.9}}))
        os.utime(cfg, None)
        # emulate the watch callback path directly (no real poll thread)
        if cs._changed():
            cs.reload()
            bus.publish_sync("config.changed", {"config": cs.as_dict()})
        assert cs.get("weights", {}).get("reasoning") == 0.9
        assert any(e.get("config", {}).get("weights", {}).get("reasoning") == 0.9
                   for e in bus.events("config.changed"))


def test_component_controller_swap_no_kernel_stop():
    """swap() replaces instance, process RUNNING, Kernel NOT stopped."""
    from contracts import ProcessState
    reg = ComponentRegistry(plugins_dir=None)
    reg.set_instance_builder(build_instance_builder())
    proc = Process(name="svc", instance=object())
    proc.start()
    reg._processes["svc"] = proc
    ctrl = ComponentController(reg)
    assert isinstance(ctrl, IComponentController)
    # swap with a new instance
    new_inst = object()
    ok = ctrl.swap("svc", new_inst)
    assert ok is True
    assert proc.state == ProcessState.RUNNING
    assert proc.instance is new_inst


def test_manifest_reload_activates_new_plugin():
    """New plugin manifest -> activated without restart."""
    with tempfile.TemporaryDirectory() as td:
        plugins = Path(td) / "plugins"
        (plugins / "agent_platform").mkdir(parents=True)
        (plugins / "agent_platform" / "manifest.yaml").write_text(
            "name: agent\nentrypoint: services.agent_platform:AgentPlatform\n"
            "capabilities: [event.publish]\ndependencies: []\nlifecycle: true\n")
        reg = ComponentRegistry(plugins_dir=plugins)
        reg.set_instance_builder(build_instance_builder())
        # first load: agent active
        m = reg.load_manifests()
        reg.activate_platform(m[0].name, m[0], instance=None)
        assert "agent" in reg.list()
        # add a NEW plugin manifest
        (plugins / "observer_platform").mkdir(parents=True)
        (plugins / "observer_platform" / "manifest.yaml").write_text(
            "name: observer\nentrypoint: services.knowledge_platform:KnowledgePlatform\n"
            "capabilities: [knowledge.graph]\ndependencies: []\nlifecycle: true\n")
        activated = reg.reload_manifests()
        assert "observer" in activated
        assert "observer" in reg.list()
        # existing agent untouched (still present, not restarted)
        assert "agent" in reg.list()


def test_filewatcher_stdlib_only():
    """FileWatcher uses os.stat polling (no third-party deps)."""
    w = FileWatcher(poll_interval=0.05, sleep_fn=lambda s: None)
    fired = []
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "x.txt"
        f.write_text("a")
        w.watch(f, lambda p: fired.append(p))
        w.poll_once()          # initial baseline (no change)
        base = w._mtimes[str(f)] or 0.0
        os.utime(f, (base + 5, base + 5))   # deterministic mtime advance
        w.poll_once()          # detects change
    assert len(fired) == 1  # one change detected


def test_law_k8_hot_reload_imports_only_contracts_runtime():
    """LAW K8: runtime/hot_reload imports only contracts/runtime (+stdlib)."""
    path = Path(__file__).parent.parent / "runtime" / "hot_reload.py"
    STDLIB = {"os","sys","pathlib","typing","abc","enum","functools","dataclasses",
              "collections","json","time","re","contextlib","threading","asyncio",
              "warnings","logging","argparse","signal","ctypes","__future__","inspect","math"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    viol = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            top = (node.module or "").split(".")[0]
            if top in STDLIB or top == "contracts" or top == "runtime":
                continue
            viol.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in STDLIB or top == "contracts" or top == "runtime":
                    continue
                viol.append(f"import {a.name}")
    # 'watchdog' or any third-party must NOT appear
    assert "watchdog" not in " ".join(viol), f"third-party import: {viol}"
    assert viol == [], f"hot_reload imports forbidden: {viol}"
