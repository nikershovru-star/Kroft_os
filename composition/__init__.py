"""composition/ — Composition Root (ADR-026, Phase B).

ЕДИНСТВЕННОЕ место создания/связывания всех компонентов ОС:
  - container_builder  — DI container (ports + adapters + services)
  - kernel_factory     — Kernel + runtime services (Supervisor/Recovery/HotReload)
  - runtime_factory    — runtime components (CapabilityRegistry)
  - adapter_factory    — concrete adapters (filesystem, exporters, watcher, server)
  - service_factory    — service wiring facade (agent, scheduler)
  - plugin_factory     — plugin loader
  - bootstrap          — system bootstrap orchestration (ADR-029 lifecycle)

Kernel НЕ создаёт ничего — получает готовое через конструктор (ADR-028).
"""
from .container_builder import build_container, _wire_agent, _wire_scheduler
from .kernel_factory import (
    build_event_bus, build_kernel, build_services, build_instance_builder, ComponentController,
)
from .runtime_factory import build_capability_registry
from .adapter_factory import build_core_adapters, build_watcher, build_server
from .service_factory import wire_agent, wire_scheduler
from .plugin_factory import build_plugin_loader
from .bootstrap import build_system, shutdown_system

__all__ = [
    "build_container", "build_event_bus", "build_kernel", "build_services",
    "build_instance_builder", "ComponentController", "build_capability_registry",
    "build_core_adapters", "build_watcher", "build_server", "wire_agent",
    "wire_scheduler", "build_plugin_loader", "build_system", "shutdown_system",
]
