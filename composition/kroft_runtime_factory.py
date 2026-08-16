"""composition/kroft_runtime_factory.py — assembly-layer factory for KroftRuntime.

ТЗ PHASE 1 STEP 3: Runtime uses the existing DI/container substrate. This module
lives in the ``composition`` package, which (per import_matrix.yaml) is the ONLY
assembly layer permitted to import everything. It injects the concrete builders
(build_container / build_kernel / KROFT_OSServer) into the axis-clean
``runtime.kroft_runtime.KroftRuntime`` so that ``runtime`` itself stays K1-clean
(imports only contracts + stdlib).

NOTE: named ``kroft_runtime_factory`` (not ``runtime_factory``) to avoid
colliding with the existing sibling ``composition/runtime_factory.py``
(build_capability_registry) — ТЗ §35: do not overwrite unrelated files.
"""

from __future__ import annotations

from typing import Optional

from composition.container_builder import build_container
from composition.kernel_factory import build_kernel
from adapters.http_server import KROFT_OSServer
from adapters.tcp_event_bus import TcpEventBus  # PHASE 5: reuse existing distributed bus (ADR-030)
from services.kroft_agent_interface import KroftAgentInterface

from runtime.kroft_runtime import KroftRuntime, RuntimeConfig


def _fed_bus_factory(container, config: RuntimeConfig):
    """PHASE 5 — build + join the distributed event bus for a Local KROFT Network.

    REUSE-FIRST (K5): uses the EXISTING ``TcpEventBus`` (adapters/tcp_event_bus.py,
    ADR-030) — no second transport/federation system. The bus implements
    IEventBus, so CognitiveKernel (build_kernel) and KroftRuntime see it as the
    normal event bus; only now events propagate across nodes.

    K1 note: this factory lives in the ``composition`` layer (permitted to import
    adapters), so ``runtime`` stays axis-clean.
    """
    port = config.network_port or (config.api_port + 1)
    bus = TcpEventBus(config.node_id, port, host=config.host)
    # TcpEventBus starts its listener inside join() (call even with an empty
    # peer list so the server socket is open and other nodes can connect to us).
    bus.join(list(config.peers))
    # Register as IEventBus so container.resolve("IEventBus") returns the mesh bus
    # for any later consumers (and KroftRuntime.stop() tears it down via the iface).
    try:
        container.register_instance("IEventBus", bus)
    except Exception:
        pass
    return bus


def build_runtime(
    config: Optional[RuntimeConfig] = None,
    *,
    node_id: str = "kroft-local",
    vault: str = "./nodes/kroft-local",
    host: str = "127.0.0.1",
    api_port: int = 8080,
    federation: bool = False,
    network_port: int = 0,
    peers: Optional[tuple] = None,
    llm: str = "none",
    embedding: str = "none",
) -> KroftRuntime:
    """Construct a fully-wired KroftRuntime for one independent KROFT instance.

    REUSE-FIRST: delegates to the existing composition root (build_container)
    and CognitiveKernel factory (build_kernel) plus the existing KROFT_OSServer.
    No second boot sequence, no duplicated wiring.

    PHASE 5 federation: when ``federation=True``, a distributed TcpEventBus (the
    existing ADR-030 substrate) is injected as the event bus and joined to
    ``peers`` — turning this Runtime into a node of a Local KROFT Network.
    """
    cfg = config or RuntimeConfig(
        node_id=node_id,
        vault=vault,
        host=host,
        api_port=api_port,
        federation=federation,
        network_port=network_port,
        peers=peers or (),
        llm=llm,
        embedding=embedding,
    )
    return KroftRuntime(
        cfg,
        build_container=build_container,
        build_kernel=build_kernel,
        server_factory=KROFT_OSServer,
        agent_interface_factory=KroftAgentInterface,
        event_bus_factory=_fed_bus_factory if federation else None,
    )
