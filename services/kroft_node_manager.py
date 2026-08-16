"""KROFT-NET-02 — Local Node Manager (TZ §4/§5/§21/§22).

Thin orchestration layer for running several independent KROFT OS instances on
one machine. REUSE: it launches the EXISTING ``run_kroft.py`` composition root as a
subprocess per node (each with its own ``--state-root`` + ``--node_id`` + ``--port``).
It does NOT build a second federation, transport, or identity system — those already
exist (ADR-030) and are reused by the booted nodes themselves.

This is the LOCAL analog of the operator surface Hermes will drive (KROFT-NET-04).
Manager responsibilities (TZ §4):
    start(node)  stop(node)  restart(node)  status(node)  list_nodes()
    connect/disconnect are federation concerns owned by the booted nodes, not here.

KROFT-NET-01 guarantee: each node gets a distinct ``<state_root>/<node_id>/`` dir
(TZ §6/§30/§31) so no mutable state is shared between instances.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


@dataclass
class NodeSpec:
    """Declarative description of one local KROFT node (TZ §22)."""

    id: str
    role: str = "generic"
    port: int = 7101
    state_root: str = ""
    extra_args: List[str] = field(default_factory=list)

    def resolved_state_root(self, base: Optional[str] = None) -> str:
        if self.state_root:
            return self.state_root
        base = base or os.path.join(os.getcwd(), ".kroft", "nodes")
        return os.path.join(base, self.id)


@dataclass
class NodeStatus:
    node_id: str
    running: bool
    pid: Optional[int] = None
    port: Optional[int] = None
    state_root: Optional[str] = None


class KroftNodeManager:
    """Manages independent local KROFT OS subprocesses (TZ §4/§5)."""

    def __init__(self, base_state_root: Optional[str] = None) -> None:
        self._base = base_state_root or os.path.join(os.getcwd(), ".kroft", "nodes")
        self._procs: Dict[str, subprocess.Popen] = {}
        self._specs: Dict[str, NodeSpec] = {}

    # --- declarative config (TZ §22) ---
    def load_config(self, path: str) -> List[NodeSpec]:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        specs: List[NodeSpec] = []
        for raw in data.get("nodes", []):
            spec = NodeSpec(
                id=raw["id"],
                role=raw.get("role", "generic"),
                port=int(raw.get("port", 7101)),
                state_root=raw.get("state_root", ""),
                extra_args=list(raw.get("extra_args", [])),
            )
            specs.append(spec)
            self._specs[spec.id] = spec
        return specs

    # --- lifecycle ---
    def start(self, spec: NodeSpec) -> subprocess.Popen:
        if spec.id in self._procs and self._procs[spec.id].poll() is None:
            return self._procs[spec.id]  # already running
        state_root = spec.resolved_state_root(self._base)
        os.makedirs(state_root, exist_ok=True)
        cmd = [
            sys.executable, "run_kroft.py",
            "--node_id", spec.id,
            "--state-root", state_root,
            "--port", str(spec.port),
            "--no-demo",
            "--llm", "none",
            "--embedding", "none",
            "--agent-runtime", "off",
        ] + list(spec.extra_args)
        proc = subprocess.Popen(
            cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self._procs[spec.id] = proc
        self._specs[spec.id] = spec
        return proc

    def stop(self, node_id: str) -> bool:
        proc = self._procs.get(node_id)
        if proc is None or proc.poll() is not None:
            self._procs.pop(node_id, None)
            return False
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._procs.pop(node_id, None)
        return True

    def restart(self, node_id: str) -> subprocess.Popen:
        spec = self._specs.get(node_id)
        if spec is None:
            raise KeyError(f"unknown node: {node_id}")
        self.stop(node_id)
        return self.start(spec)

    def status(self, node_id: str) -> NodeStatus:
        proc = self._procs.get(node_id)
        spec = self._specs.get(node_id)
        running = proc is not None and proc.poll() is None
        return NodeStatus(
            node_id=node_id,
            running=running,
            pid=proc.pid if running else None,
            port=spec.port if spec else None,
            state_root=spec.resolved_state_root(self._base) if spec else None,
        )

    def list_nodes(self) -> List[NodeStatus]:
        return [self.status(nid) for nid in self._specs]

    def shutdown_all(self) -> None:
        for nid in list(self._procs.keys()):
            self.stop(nid)
