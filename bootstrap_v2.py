"""bootstrap_v2.py — Runtime Host entrypoint (delegates to Composition Root).

Вся сборка перенесена в composition/ (Phase B.1). Этот модуль — тонкий
orchestrатор для режимов runtime-host (kernel-only / with-components / services).
См. ADR-029 Bootstrap Lifecycle.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Optional

from composition import build_container, build_event_bus, build_kernel, build_services
from composition.bootstrap import build_system, shutdown_system
from runtime.kernel_runtime import run


def main() -> int:
    parser = argparse.ArgumentParser(prog="bootstrap_v2", description="KROFT_OS Runtime Host")
    parser.add_argument("--mode", default="kernel-only",
                        choices=["kernel-only", "with-components", "services"])
    parser.add_argument("--node-id", default="local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--peer", default=None)
    parser.add_argument("--plugins-dir", default=None)
    args = parser.parse_args()

    plugins_dir = Path(args.plugins_dir) if args.plugins_dir else (Path.cwd() / "plugins")
    kernel, container, services = build_system(
        vault_path=".", plugin_dir=args.plugins_dir, mode=args.mode,
        node_id=args.node_id, port=args.port, peer=args.peer,
    )
    return run(
        kernel, mode=args.mode, node_id=args.node_id, port=args.port,
        plugins_dir=plugins_dir if plugins_dir.exists() else None,
        instance_builder=None,
        services_factory=lambda k: services,
    )


if __name__ == "__main__":
    raise SystemExit(main())
