"""composition/bootstrap.py — System bootstrap orchestration (Phase B.1, ADR-029).

Единая точка сборки ОС: process start → configuration → DI → runtime → kernel
→ plugins → services → ready. И обратно (shutdown). Вся логика сборки —
в composition/ (container_builder, kernel_factory, ...); этот модуль только
оркестрирует последовательность.

kernel ничего не создаёт (ADR-028 Kernel Purity) — всё приходит готовым.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

from composition.container_builder import build_container
from composition.kernel_factory import build_event_bus, build_kernel, build_services
from composition.plugin_factory import build_plugin_loader


def build_system(
    vault_path: str = ".",
    plugin_dir: Optional[str] = None,
    desktop_adapter: str = "mock",
    mode: str = "kernel-only",
    node_id: str = "local",
    port: int = 8000,
    peer: Optional[str] = None,
) -> Any:
    """Bootstrap the full KROFT_OS runtime.

    Sequence (ADR-029 Bootstrap Lifecycle):
      1. configuration  — resolve vault + plugin dir
      2. DI            — build_container (ports + adapters + services)
      3. runtime       — capability registry (inside container)
      4. kernel        — build_kernel(bus)
      5. plugins       — loader.apply_exporters / apply_agent_extensions
      6. services      — runtime services (supervisor, recovery, hot-reload)
      7. ready         — return (kernel, container, services)
    """
    loader = build_plugin_loader(plugin_dir)
    container = build_container(vault_path, loader=loader, desktop_adapter=desktop_adapter)
    bus = build_event_bus()
    if not container.has("IEventBus"):
        container.register_instance("IEventBus", bus)
    kernel = build_kernel(bus=bus)
    plugins_dir = Path(plugin_dir) if plugin_dir else (Path.cwd() / "plugins")
    services = build_services(kernel, bus, plugins_dir if plugins_dir.exists() else None)
    return kernel, container, services


def shutdown_system(kernel: Any, services: list) -> None:
    """Reverse lifecycle: stop services → stop kernel."""
    for svc in services:
        try:
            if hasattr(svc, "stop"):
                svc.stop()
        except Exception:
            pass
    try:
        kernel.stop()
    except Exception:
        pass
