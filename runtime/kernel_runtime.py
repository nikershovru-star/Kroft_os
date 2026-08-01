"""KROFT_OS v3.0 — Runtime Host (Phase 2 + Phase 3: Platform + Services).

Lives in `runtime/` -> may import ONLY `contracts.*` + local runtime modules
(arch-gate LAW K8). Does NOT import the concrete `kernel` package and does NOT
create a `Kernel` — the concrete Kernel is injected from the composition root
(bootstrap_v2.py, outside the scanned packages).

Phase 2: manifest-based platform integration (ComponentRegistry, no wrappers).
Phase 3: Runtime Services (Observability) hang on the event bus and observe
lifecycle/metrics/config/snapshots — they never import domain platforms (LAW K3).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from contracts import IKernel, LifecycleState

from runtime.runtime_state import RuntimeState
from runtime.signal_handler import install_signal_handlers
from runtime.component_registry import ComponentRegistry
from runtime.runtime_host import RuntimeHost


def run(
    kernel: IKernel,
    mode: str = "kernel-only",
    node_id: str = "local",
    port: int = 8000,
    plugins_dir: Optional[Path] = None,
    instance_builder: Optional[Callable[[str, Any], Any]] = None,
    services_factory: Optional[Callable[[IKernel], List[Any]]] = None,
) -> int:
    """Drive an injected IKernel through its lifecycle (no kernel import here)."""
    state = RuntimeState(kernel)
    install_signal_handlers(kernel)

    registry = ComponentRegistry(plugins_dir=plugins_dir)
    registry.bind(kernel)
    host = RuntimeHost(registry)

    components: Dict[str, Any] = {}
    services: List[Any] = []
    try:
        kernel.initialize()
        kernel.start()
        state.mark_running()
        print(f"[runtime] node={node_id} port={port} — Kernel READY "
              f"(extending IKernel, no wrappers)")

        if mode in ("with-components", "services"):
            manifests = host.discover()
            print(f"[runtime] discovered {len(manifests)} component manifest(s)")
            components = host.activate(instance_builder=instance_builder)
            for name, status in components.items():
                print(f"[runtime] component {name}: {status}")

        # Phase 3: Runtime Services observe via the event bus.
        if mode == "services" and services_factory is not None:
            services = services_factory(kernel)
            for svc in services:
                if hasattr(svc, "start"):
                    svc.start()
            print(f"[runtime] {len(services)} runtime service(s) started")

        # Block so SIGINT can arrive (graceful shutdown path).
        while kernel.state == LifecycleState.RUNNING:
            time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        kernel.stop()
        state.mark_stopped()
        for svc in services:
            if hasattr(svc, "stop"):
                try:
                    svc.stop()
                except Exception:
                    pass
        registry.stop_all()
        print("[runtime] Kernel stopped; services + components stopped")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"[runtime] FAILED to start: {exc}", file=sys.stderr)
        state.mark_failed()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="runtime", description="KROFT_OS Runtime Host")
    parser.add_argument("--mode", default="kernel-only",
                        choices=["kernel-only", "with-components", "services"])
    parser.add_argument("--node-id", default="local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--peer", default=None)
    parser.add_argument("--plugins-dir", default=None,
                        help="path to plugins/ directory (default: ./plugins)")
    args = parser.parse_args()

    try:
        from bootstrap_v2 import (
            build_kernel,
            build_instance_builder,
            build_event_bus,
            build_services,
        )
    except Exception as exc:  # pragma: no cover
        print(f"[runtime] composition root unavailable: {exc}", file=sys.stderr)
        return 1

    plugins_dir = Path(args.plugins_dir) if args.plugins_dir else (Path.cwd() / "plugins")
    bus = build_event_bus()
    kernel = build_kernel(bus=bus)
    builder = build_instance_builder()
    services_factory = (lambda k: build_services(k, bus)) if args.mode == "services" else None
    return run(
        kernel,
        mode=args.mode,
        node_id=args.node_id,
        port=args.port,
        plugins_dir=plugins_dir if plugins_dir.exists() else None,
        instance_builder=builder,
        services_factory=services_factory,
    )
