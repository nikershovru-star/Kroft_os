"""bootstrap_v2.py — Composition Root v2 (Runtime Host, variant b).

Lives at the project root (OUTSIDE the arch-gate scanned packages), so it may
import both `kernel` (concrete) and `runtime` (component layer). It wires the
concrete `Kernel` (which implements contracts.IKernel) into the runtime host.

Does NOT duplicate the kernel, does NOT create wrapper adapters. Components load
by manifest through ComponentRegistry.
"""
from __future__ import annotations

import sys

from kernel import Kernel  # concrete microkernel (implements contracts.IKernel)
from runtime.kernel_runtime import run


def build_kernel() -> Kernel:
    """Construct the concrete Kernel (implements IKernel)."""
    return Kernel()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="bootstrap_v2", description="KROFT_OS Composition Root v2")
    parser.add_argument("--mode", default="kernel-only", choices=["kernel-only"])
    parser.add_argument("--node-id", default="local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--peer", default=None)
    args = parser.parse_args()

    kernel = build_kernel()
    return run(kernel, node_id=args.node_id, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
