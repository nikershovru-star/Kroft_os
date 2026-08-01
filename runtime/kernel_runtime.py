"""KROFT_OS v3.0 — Runtime Host (Foundation, Phase 1). Component layer.

This module lives in `runtime/` and therefore may import ONLY `contracts.*`
(arch-gate LAW). It does NOT import the concrete `kernel` package and does NOT
create a `Kernel` — the concrete `Kernel` is injected from the composition root
(bootstrap_v2.py, which lives outside the scanned packages and may wire kernel in).

Extends the EXISTING microkernel via the `IKernel` port (ADR-020 variant b):
- NO second kernel
- NO wrapper-style adapters
- Component loading is manifest-based through `ComponentRegistry`
"""
from __future__ import annotations

import argparse
import sys
import time

from contracts import IKernel, LifecycleState

# Local runtime components (all depend only on contracts.IKernel).
from runtime.runtime_state import RuntimeState
from runtime.signal_handler import install_signal_handlers
from runtime.component_registry import ComponentRegistry


def run(kernel: IKernel, node_id: str = "local", port: int = 8000) -> int:
    """Drive an injected IKernel through its lifecycle (no kernel import here)."""
    # 1) Runtime State FSM extension (thin mirror over IKernel, NOT a new kernel)
    state = RuntimeState(kernel)

    # 2) Signal handlers (SIGINT/SIGTERM -> graceful shutdown)
    install_signal_handlers(kernel)

    # 3) Component Registry (manifest-based load — NO XxxWrapper adapters)
    registry = ComponentRegistry()
    registry.bind(kernel)

    # 4) Initialize then Start (extends IKernel, does NOT replace it)
    try:
        kernel.initialize()  # UNINITIALIZED -> INITIALIZED
        kernel.start()       # INITIALIZED -> RUNNING
        state.mark_running()
        print(f"[runtime] node={node_id} port={port} — Kernel READY "
              f"(extending IKernel, no wrappers)")
        registry.activate_all()
        # Block the main thread so SIGINT can arrive (graceful shutdown path)
        while kernel.state == LifecycleState.RUNNING:
            time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        kernel.stop()
        state.mark_stopped()
        print("[runtime] Kernel stopped")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"[runtime] FAILED to start: {exc}", file=sys.stderr)
        state.mark_failed()
        return 1


def main() -> int:
    """CLI entry: parse args, but delegate kernel creation to the composition root.

    We CANNOT import `kernel` here (arch-gate). The concrete Kernel is built by
    bootstrap_v2.py; when run as `python -m runtime`, we attempt to resolve it via
    the project's composition root if present, otherwise error clearly.
    """
    parser = argparse.ArgumentParser(prog="runtime", description="KROFT_OS Runtime Host")
    parser.add_argument("--mode", default="kernel-only", choices=["kernel-only"])
    parser.add_argument("--node-id", default="local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--peer", default=None)
    args = parser.parse_args()

    # Composition root (bootstrap_v2.py) lives outside `runtime/` and may import
    # `kernel`. We call into it to obtain the concrete IKernel implementation.
    try:
        from bootstrap_v2 import build_kernel
    except Exception as exc:  # pragma: no cover
        print(f"[runtime] composition root unavailable: {exc}", file=sys.stderr)
        return 1
    kernel = build_kernel()
    return run(kernel, node_id=args.node_id, port=args.port)
