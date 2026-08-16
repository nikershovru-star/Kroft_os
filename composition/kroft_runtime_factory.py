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
from services.kroft_agent_interface import KroftAgentInterface

from runtime.kroft_runtime import KroftRuntime, RuntimeConfig


def build_runtime(
    config: Optional[RuntimeConfig] = None,
    *,
    node_id: str = "kroft-local",
    vault: str = "./nodes/kroft-local",
    host: str = "127.0.0.1",
    api_port: int = 8080,
    federation: bool = False,
    llm: str = "none",
    embedding: str = "none",
) -> KroftRuntime:
    """Construct a fully-wired KroftRuntime for one independent KROFT instance.

    REUSE-FIRST: delegates to the existing composition root (build_container)
    and CognitiveKernel factory (build_kernel) plus the existing KROFT_OSServer.
    No second boot sequence, no duplicated wiring.
    """
    cfg = config or RuntimeConfig(
        node_id=node_id,
        vault=vault,
        host=host,
        api_port=api_port,
        federation=federation,
        llm=llm,
        embedding=embedding,
    )
    return KroftRuntime(
        cfg,
        build_container=build_container,
        build_kernel=build_kernel,
        server_factory=KROFT_OSServer,
        agent_interface_factory=KroftAgentInterface,
    )
