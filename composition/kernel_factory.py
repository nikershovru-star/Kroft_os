"""composition/kernel_factory.py — Kernel + Runtime services assembly (Phase B.1).

Перенесено из bootstrap_v2.py. Composition Root формирует Kernel и runtime-сервисы
(Supervisor, Recovery, Hot Reload, Metrics, Logging, Config, Snapshot).

ВНИМАНИЕ: build_kernel пока передаёт container в Kernel (совместимость). В B.2
Kernel перейдёт на constructor injection (runtime, event_bus, state_repository,
services, registry) — см. ADR-029 Bootstrap Lifecycle.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, List, Optional

from infrastructure import DependencyContainer, InMemoryEventBus
from infrastructure.metrics import PsutilMetricsCollector
from kernel import Kernel
from runtime.kernel_runtime import run
from runtime.manifest_schema import Manifest
from runtime.services import ConfigService, LoggingService, MetricsService, SnapshotService
from contracts import IEventBus, IProcessRegistry, IComponentController
from runtime.component_registry import ComponentRegistry
from runtime.hot_reload import HotReloadService
from runtime.supervisor import HealthMonitor, RecoveryPolicyRegistry, SupervisorService
from runtime.recovery import RecoveryJournal, RecoveryState


def build_event_bus() -> InMemoryEventBus:
    """Single shared event bus (Kernel + services both use this instance)."""
    return InMemoryEventBus()


def build_kernel(bus: Optional[IEventBus] = None) -> Kernel:
    """Construct the concrete Kernel with the shared IEventBus wired in."""
    container = DependencyContainer()
    if bus is not None:
        container.register_instance("IEventBus", bus)
    return Kernel(container=container)


def build_instance_builder() -> Callable[[str, Manifest], Optional[Any]]:
    """Return a builder that supplies real platform instances where possible."""
    def builder(name: str, manifest: Manifest) -> Optional[Any]:
        if name == "autonomy":
            try:
                from services.threshold_autonomy_controller import ThresholdAutonomyController
                return ThresholdAutonomyController()
            except Exception:
                return None
        return None
    return builder


def build_services(kernel: Any, bus: IEventBus, plugins_dir: Optional[Path] = None) -> List[Any]:
    """Construct the Phase 3 + 4 + 5 runtime services, shared bus."""
    if bus is None:
        return []
    logger = LoggingService()
    collector = PsutilMetricsCollector()
    registry: Optional[IProcessRegistry] = None

    comp_registry = ComponentRegistry(plugins_dir=plugins_dir)
    comp_registry.set_instance_builder(build_instance_builder())
    controller = ComponentController(comp_registry)
    policies = RecoveryPolicyRegistry.from_dict({
        "database": {"restart": True, "max_attempts": 10},
        "llm_worker": {"restart": True, "max_attempts": 3},
        "human_approval": {"restart": False},
    })
    journal = RecoveryJournal()
    recovery_state = RecoveryState(policies._policies)
    supervisor = SupervisorService(
        bus=bus, registry=comp_registry, controller=controller,
        policies=policies, journal=journal, state=recovery_state, logger=logger,
    )
    health = HealthMonitor(bus=bus, registry=comp_registry, logger=logger)

    config_service = ConfigService(bus=bus, logger=logger)
    hot_reload = HotReloadService(
        bus=bus, config_service=config_service, registry=comp_registry,
        config_path=Path.cwd() / "config.json", plugins_dir=plugins_dir, logger=logger,
    )

    services: List[Any] = [
        logger,
        MetricsService(bus=bus, collector=collector, registry=registry, logger=logger),
        config_service,
        SnapshotService(bus=bus, registry=registry, logger=logger),
        supervisor,
        health,
        hot_reload,
    ]
    try:
        config_service.start_watching()
        hot_reload.start()
    except Exception:
        pass
    return services


class ComponentController(IComponentController):
    """Concrete IComponentController (composition root only)."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self._registry = registry

    def restart(self, component_name: str) -> bool:
        manifest = self._registry.get_manifest(component_name)
        instance = None
        if manifest is not None and self._registry._instance_builder is not None:
            try:
                instance = self._registry._instance_builder(component_name, manifest)
            except Exception:
                instance = None
        return self._registry.reactivate(component_name, instance)

    def swap(self, component_name: str, new_instance: Any) -> bool:
        return self._registry.swap(component_name, new_instance)
