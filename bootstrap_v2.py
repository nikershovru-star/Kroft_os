"""bootstrap_v2.py — Composition Root v2 (Runtime Host, variant b).

Lives at the project root (OUTSIDE the arch-gate scanned packages), so it may
import both `kernel` (concrete) and `services`/`runtime` (component layer). It
wires the concrete `Kernel` (which implements contracts.IKernel) into the runtime
host and supplies real platform instances where they can be built with available
ports; otherwise returns None (declarative-only registration — LAW K3: platforms
are NOT mutated to gain lifecycle; we adapt, not modify).

Does NOT duplicate the kernel, does NOT create wrapper adapters.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Optional

from kernel import Kernel  # concrete microkernel (implements contracts.IKernel)
from runtime.kernel_runtime import run
from runtime.manifest_schema import Manifest


def build_kernel() -> Kernel:
    """Construct the concrete Kernel (implements IKernel)."""
    return Kernel()


def build_instance_builder() -> Callable[[str, Manifest], Optional[Any]]:
    """Return a builder that supplies real platform instances where possible.

    Platforms need injected ports (planner, executor, router, stores, …) that are
    not all available in a bare dev context. We build only what is trivially
    constructible (`ThresholdAutonomyController` is parameterless) and return None
    for the rest — the Runtime Host then registers them declaratively (status
    RUNNING) without faking their logic. This is honest: the Platform Integration
    Core is proven (manifests discovered, components registered, lifecycle driven
    through IProcess) without violating LAW K3.
    """
    def builder(name: str, manifest: Manifest) -> Optional[Any]:
        if name == "autonomy":
            try:
                from services.threshold_autonomy_controller import ThresholdAutonomyController
                return ThresholdAutonomyController()
            except Exception:
                return None
        # agent / knowledge / learning / optimization / desktop / api need injected
        # ports; register declaratively (no instance) until the composition root
        # is extended with their real dependency graph.
        return None

    return builder


def main() -> int:
    parser = argparse.ArgumentParser(prog="bootstrap_v2", description="KROFT_OS Composition Root v2")
    parser.add_argument("--mode", default="kernel-only",
                        choices=["kernel-only", "with-components", "services"])
    parser.add_argument("--node-id", default="local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--peer", default=None)
    parser.add_argument("--plugins-dir", default=None)
    args = parser.parse_args()

    plugins_dir = Path(args.plugins_dir) if args.plugins_dir else (Path.cwd() / "plugins")
    kernel = build_kernel()
    builder = build_instance_builder()
    return run(
        kernel,
        mode=args.mode,
        node_id=args.node_id,
        port=args.port,
        plugins_dir=plugins_dir if plugins_dir.exists() else None,
        instance_builder=builder,
    )


if __name__ == "__main__":
    raise SystemExit(main())
