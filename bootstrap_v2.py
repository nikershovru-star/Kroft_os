"""bootstrap_v2.py — Composition Root v2 (Runtime Host, variant b).

Lives at the project root (OUTSIDE the arch-gate scanned packages), so it may
import both `kernel` (concrete) and `services`/`runtime` (component layer). It
wires the concrete `Kernel` (which implements contracts.IKernel) into the runtime
host, injects the shared IEventBus, and supplies real platform instances where
they can be built with available ports; otherwise returns None (declarative-only
registration — LAW K3: platforms are NOT mutated to gain lifecycle; we adapt, not
modify).

Does NOT duplicate the kernel, does NOT create wrapper adapters. The single
InMemoryEventBus instance is shared by Kernel (via its container) and the Phase 3
Runtime Services (via build_services) — so kernel.lifecycle events reach service
subscribers.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, List, Optional

from infrastructure import DependencyContainer
from infrastructure.eventbus import InMemoryEventBus
from infrastructure.metrics import PsutilMetricsCollector

from kernel import Kernel  # concrete microkernel (implements contracts.IKernel)
from runtime.kernel_runtime import run
from runtime.manifest_schema import Manifest
from runtime.services import (
    ConfigService,
    LoggingService,
    MetricsService,
    SnapshotService,
)
from contracts import IEventBus, IProcessRegistry, IComponentController
from runtime.component_registry import ComponentRegistry
from runtime.supervisor import (
    HealthMonitor,
    RecoveryPolicyRegistry,
    SupervisorService,
)
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


def build_services(kernel: Any, bus: IEventBus) -> List[Any]:
    """Construct the Phase 3 + Phase 4 runtime services, injected with the shared bus.

    Services observe via IEventBus; they never import domain platforms (LAW K3).
    The bus is the single shared instance wired into Kernel (via its container)
    and into the services, so kernel.lifecycle events reach the service subscribers.
    (We pass `bus` explicitly rather than reading kernel.event_bus, because the
    latter is only populated after Kernel.initialize().)

    Phase 4 adds the SupervisorService (autonomous recovery) wired through an
    IComponentController that delegates restart to the ComponentRegistry +
    InstanceBuilder — so the Supervisor stays ignorant of how/where/which platform
    is built (LAW K8 preserved).
    """
    if bus is None:
        return []
    logger = LoggingService()
    collector = PsutilMetricsCollector()
    # A ProcessRegistry view over the kernel's wired components is not available
    # at this layer; MetricsService tolerates registry=None (counts only).
    registry: Optional[IProcessRegistry] = None

    # Phase 4: autonomous recovery wiring.
    comp_registry = ComponentRegistry(plugins_dir=None)
    comp_registry.set_instance_builder(build_instance_builder())
    controller = ComponentController(comp_registry)
    policies = RecoveryPolicyRegistry.from_dict({
        # Different components, different policies (per Phase 4 spec examples).
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

    services: List[Any] = [
        logger,
        MetricsService(bus=bus, collector=collector, registry=registry, logger=logger),
        ConfigService(bus=bus, logger=logger),
        SnapshotService(bus=bus, registry=registry, logger=logger),
        supervisor,
        health,
    ]
    return services


class ComponentController(IComponentController):
    """Concrete IComponentController (composition root only).

    Restart delegates to ComponentRegistry.reactivate, which uses the injected
    InstanceBuilder to rebuild the platform instance. The Supervisor sees ONLY
    this port — it never learns how/where/which platform is built (LAW K8).
    """

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
    bus = build_event_bus()
    kernel = build_kernel(bus=bus)
    builder = build_instance_builder()
    services_factory = lambda k: build_services(k, bus)
    return run(
        kernel,
        mode=args.mode,
        node_id=args.node_id,
        port=args.port,
        plugins_dir=plugins_dir if plugins_dir.exists() else None,
        instance_builder=builder,
        services_factory=services_factory,
    )


if __name__ == "__main__":
    raise SystemExit(main())
