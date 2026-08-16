"""PHASE 1 — KROFT Runtime (lifecycle orchestration only, K1 axis-clean).

Единый жизненный цикл KROFT: start → boot (CognitiveKernel + Knowledge +
Memory + SemanticIndex + Identity + Trust) → HTTP API → health → stop → recover.

Архитектурные инварианты ТЗ PHASE 1:
  - Runtime НЕ содержит бизнес-логики CognitiveKernel (search/query/
    reasoning/LLM/federation/trust-policy). Он ТОЛЬКО оркеструет уже
    существующие компоненты.
  - K1 AXIS-CLEAN (import_matrix.yaml: ``runtime.* -> contracts + stdlib``):
    этот модуль импортирует ТОЛЬКО ``contracts`` + stdlib. Concrete builders
    (build_container / build_kernel / KROFT_OSServer) инжектируются из
    composition-слоя (assembly layer) через ``composition/runtime_factory.py``.
    Runtime НЕ импортирует ``composition`` / ``adapters`` напрямую — это
    предотвращает нарушение K1 и держит Runtime тестируемым (DI).
  - REUSE-FIRST (K5): Runtime переиспользует existing build_container +
    build_kernel + KROFT_OSServer. НЕ создаёт второго boot-sequence, НЕ
    дублирует node manager (services/kroft_node_manager.py), НЕ переписывает
    KROFT_OSServer endpoint-логику.
  - KROFT = самостоятельный Runtime; Hermes/Codex/Claude/CLI = внешние клиенты.
    Runtime НЕ импортирует ничего agent-специфичного.
  - Per-instance state: каждый Runtime имеет собственный vault (storage_root),
    node_id, host, api_port. НЕТ shared mutable state между инстансами.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class RuntimeConfig:
    """Per-instance configuration for one independent KROFT Runtime.

    Each field maps to an existing constructor/param — no new config system.
    storage_root == vault passed to build_container (isolated per node).
    """

    node_id: str = "kroft-local"
    vault: str = "./nodes/kroft-local"
    host: str = "127.0.0.1"
    api_port: int = 8080
    # Federation is wired in a later phase; PHASE 1 leaves it off by default
    # (ТЗ PHASE 1 scope: single independent runtime + HTTP API, no federation yet).
    federation: bool = False
    # Optional LLM/embedding wiring is deferred to later phases; PHASE 1 boots
    # read-only-capable runtime (graph + semantic index from foundation snapshot).
    llm: str = "none"
    embedding: str = "none"


# Injectable builder signatures (KEPT as runtime-local type aliases to avoid
# importing composition/adapters at module top-level — K1 axis-clean).
ContainerBuilder = Callable[[str], Any]
KernelBuilder = Callable[[Any, Any], Any]
ServerFactory = Callable[..., Any]
AgentInterfaceFactory = Callable[..., Any]


class KroftRuntime:
    """Lifecycle owner for one independent KROFT OS instance.

    Responsibilities (ТЗ STEP 2): start / stop / health / is_running.
    Everything else is delegated to existing components injected by the
    composition/assembly layer.

    Builders MUST be injected (ТЗ §35: runtime is axis-clean, it cannot import
    composition/adapters directly). Use ``composition.runtime_factory.build_runtime``
    to obtain a fully-wired instance, or pass builders explicitly in tests.
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        *,
        build_container: Optional[ContainerBuilder] = None,
        build_kernel: Optional[KernelBuilder] = None,
        server_factory: Optional[ServerFactory] = None,
        agent_interface_factory: Optional[AgentInterfaceFactory] = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self._build_container = build_container
        self._build_kernel = build_kernel
        self._server_factory = server_factory
        self._agent_interface_factory = agent_interface_factory
        self._container: Optional[Any] = None
        self._kernel: Optional[Any] = None
        self._server: Optional[Any] = None
        self._agent_interface: Optional[Any] = None
        self._started_at: Optional[float] = None
        self._running = False

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> "KroftRuntime":
        """Boot the CognitiveKernel + services + HTTP API (idempotent-safe)."""
        if self._running:
            return self
        # All three builders are required; they are injected from the
        # composition/assembly layer (К1 axis-clean).
        if not (self._build_container and self._build_kernel and self._server_factory):
            raise RuntimeError(
                "KroftRuntime requires build_container/build_kernel/server_factory "
                "injected from the composition layer (use build_runtime())."
            )
        # 1) Composition root — DI container (composition/container_builder).
        #    build_container already loads the foundation snapshot (graph +
        #    index + semantic vectors) when KROFT_KNOWLEDGE_FOUNDATION exists.
        self._container = self._build_container(self.config.vault)
        # 2) Shared event bus (resolved from container, single instance).
        bus = self._container.resolve("IEventBus")
        # 3) CognitiveKernel (composition/kernel_factory.build_kernel).
        self._kernel = self._build_kernel(bus, self._container)
        # 4) Universal Agent Interface (PHASE 2) — delegate facade over the
        #    running container + this runtime (no agent-specific logic inside).
        #    MUST be created AND registered into the container BEFORE the HTTP
        #    server starts accepting requests, so there is no race window where
        #    /api/status|query|resolve|audit hit a missing interface (ТЗ §PHASE3.1).
        if self._agent_interface_factory is not None:
            self._agent_interface = self._agent_interface_factory(
                self._container, self
            )
            self._container.register_instance(
                "IKroftAgentInterface", self._agent_interface
            )
        # 5) HTTP API — reuse existing KROFT_OSServer (adapters/http_server).
        #    It resolves "IKroftAgentInterface" from the container (set above),
        #    so the interface is already present when requests arrive.
        self._server = self._server_factory(
            self._container, host=self.config.host, port=self.config.api_port
        )
        self._server.start()
        self._started_at = time.time()
        self._running = True
        return self

    def stop(self) -> None:
        """Graceful shutdown. Idempotent: calling twice is a no-op."""
        # Stop HTTP server first (release the port), then kernel if needed.
        if self._server is not None:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        # No kernel.shutdown exists in the current API; the kernel holds no
        # background threads of its own in this boot path, so dropping refs is
        # sufficient (ТЗ STEP 7: no orphan threads). Event bus is in-memory.
        self._kernel = None
        self._agent_interface = None
        self._container = None
        self._running = False
        self._started_at = None

    @property
    def is_running(self) -> bool:
        return self._running

    # --- health (ТЗ STEP 6) ------------------------------------------------
    def health(self) -> Dict[str, Any]:
        """Minimal machine-readable health contract.

        No distributed/federation/AI self-diagnostics yet (ТЗ STEP 6 scope).
        """
        if not self._running or self._server is None:
            return {
                "status": "down",
                "runtime": "stopped",
                "kernel": "n/a",
                "knowledge": "n/a",
                "http": "n/a",
            }
        # HTTP server alive?
        http_ready = False
        try:
            http_ready = self._server.port is not None
        except Exception:
            http_ready = False
        # Knowledge loaded? probe the graph via the container engine.
        knowledge_ready = False
        try:
            engine = self._container.resolve("GraphQueryEngine")
            knowledge_ready = bool(engine._snapshot().get("nodes"))
        except Exception:
            knowledge_ready = False
        return {
            "status": "ok",
            "node_id": self.config.node_id,
            "runtime": "running",
            "kernel": "ready" if self._kernel is not None else "down",
            "knowledge": "ready" if knowledge_ready else "empty",
            "http": "ready" if http_ready else "down",
            "api_port": self._server.port,
            "started_at": self._started_at,
        }

    # --- recovery (ТЗ STEP 8) ---------------------------------------------
    def recover(self) -> bool:
        """Attempt to bring a stopped/partial runtime back up.

        Reuses build_container + foundation snapshot restoration (no new
        persistence system). Returns True if (re)started successfully.
        """
        if self._running:
            return True
        try:
            self.start()
            return self._running
        except Exception:
            return False

    # --- accessors for external clients (Hermes/Codex/CLI in later phases) --
    @property
    def container(self) -> Optional[Any]:
        return self._container

    @property
    def kernel(self) -> Optional[Any]:
        return self._kernel

    @property
    def server(self) -> Optional[Any]:
        return self._server

    @property
    def agent_interface(self) -> Optional[Any]:
        """Universal Agent Interface facade (PHASE 2) for external agents."""
        return self._agent_interface
