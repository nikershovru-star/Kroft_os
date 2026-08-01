"""(composition root) KROFT_OS bootstrap — the single entry point of the OS.

Replaces the legacy `main.py` as the canonical `python bootstrap.py`. Wires the
Wave 3-14 platforms into one runtime through the DI container, selects the LLM
adapter (OmniRoute if reachable, else Mock — the MANDATORY offline fallback), and
starts a unified Runtime with a clear lifecycle.

Design rules (consistent with the rest of the codebase):
- This module is the ONE place that references concrete adapters/services.
  Platforms, contracts, and cli/ must never import adapters directly.
- Core boot must NEVER depend on an external backend: if OmniRoute (:20128) is
  down, MockLlmAdapter keeps the kernel alive. Absence of a network model is a
  degraded mode, not a boot failure.

Smoke contract (per spec):
  S1  python bootstrap.py        -> Kernel started / Platforms initialized /
                                    Router initialized / LLM initialized (Mock|OmniRoute) /
                                    Runtime ready
  S2  agent.ask("Hello")         -> answer via MockAdapter (or OmniRoute)
  S3  backend reachability       -> OmniRoute if :20128 up, else Mock; Runtime continues
  S4  legacy VaultCrawler         -> registered as a platform service, not launched separately
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

# --- stdlib + contracts (no adapter/service imports at module top in platforms) ---
from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import IPlanner, IExecutor, Workflow, WorkflowStatus, Step, StepStatus

# --- infrastructure: DI container + event bus ---
from infrastructure import DependencyContainer, InMemoryEventBus
from infrastructure.graph_builder import InMemoryGraphBuilder
from adapters.filesystem_adapter import LocalFileSystemAdapter

# --- adapters (composition root ONLY) ---
from adapters.omni_route_adapter import OmniRouteAdapter
from adapters.mock_llm_adapter import MockLlmAdapter

# --- services: platforms + wiring ---
from services.agent_platform import AgentPlatform
from services.memory_platform import MemoryPlatform
from services.knowledge_platform import KnowledgePlatform
from services.workflow_runner import build_executor
from adapters.rule_based_planner import RuleBasedPlanner
from services.pattern_based_optimizer import PatternBasedOptimizer
from services.simple_self_evaluator import SimpleSelfEvaluator
from services.threshold_autonomy_controller import ThresholdAutonomyController
from adapters.in_memory_learning_store import InMemoryLearningStore
from adapters.in_memory_memory_store import InMemoryMemoryStore

# Policy engine + router (Wave 5 / Wave 6)
try:
    from services.policy_engine import PolicyEngine
    from contracts.i_policy import PolicyContext as _PC
    from contracts.model_registry import ModelRegistry
    _HAVE_POLICY = True
except Exception:  # pragma: no cover - policy engine is optional at boot
    _HAVE_POLICY = False

from adapters.router import Router


DEFAULT_CONFIG = {
    "llm": {
        "backend": "omniroute",          # "omniroute" | "mock"
        "base_url": "http://localhost:20128/v1",
        "api_key": "[REDACTED]",
        "model": "auto",
        "timeout": 60.0,
    },
    "runtime": {
        "session_id": None,             # auto-generated if None
        "vault_path": None,              # legacy VaultCrawler mount (optional)
        "enable_autonomy": True,
    },
}


def load_config(path: Optional[str]) -> Dict[str, Any]:
    """Load bootstrap config from a JSON/YAML file, merged over DEFAULT_CONFIG.

    YAML is optional (pyyaml may be absent); JSON is always supported so the
    core never hard-depends on a parser.
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if not path:
        return cfg
    if not os.path.exists(path):
        print(f"[config] file not found: {path} — using defaults")
        return cfg
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
            user = yaml.safe_load(text) or {}
        except Exception as exc:
            print(f"[config] YAML parse failed ({exc}); falling back to JSON")
            try:
                user = json.loads(text)
            except Exception:
                user = {}
    else:
        try:
            user = json.loads(text)
        except Exception as exc:
            print(f"[config] JSON parse failed ({exc}) — using defaults")
            return cfg
    # shallow merge top-level keys
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def build_llm_factory(cfg: Dict[str, Any]) -> ILlm:
    """LLM Factory (spec diagram): OmniRoute if reachable, else Mock fallback.

    MockLlmAdapter is the MANDATORY fallback — it is always returned as a second
    entry so the Router can degrade gracefully and the kernel always boots.
    """
    llm_cfg = cfg.get("llm", {})
    backend = llm_cfg.get("backend", "omniroute")
    mock = MockLlmAdapter()

    if backend == "mock":
        print("LLM initialized (Mock)")
        return mock

    # Try OmniRoute; fall back to Mock on any failure (no network = no boot fail).
    try:
        omni = OmniRouteAdapter(
            base_url=llm_cfg.get("base_url", "http://localhost:20128/v1"),
            api_key=llm_cfg.get("api_key", "[REDACTED]"),
            model=llm_cfg.get("model", "auto"),
            timeout=float(llm_cfg.get("timeout", 60.0)),
        )
        if omni.ping():
            print("LLM initialized (OmniRoute)")
            return omni
        print("LLM initialized (Mock) — OmniRoute unreachable, using fallback")
    except Exception as exc:  # noqa: BLE001
        print(f"LLM initialized (Mock) — OmniRoute error: {exc}")
    return mock


def build_container(cfg: Dict[str, Any], llm: ILlm) -> DependencyContainer:
    """Build the DI container and register all platform instances."""
    c = DependencyContainer()
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("LLM", llm)
    # Legacy filesystem + graph builder (needed to mount the legacy VaultCrawler
    # as a platform service in S4 without rewriting it).
    vault_path = cfg["runtime"].get("vault_path")
    if vault_path:
        c.register_instance("IFileSystem", LocalFileSystemAdapter(vault_path))
        c.register_instance("IGraphBuilder", InMemoryGraphBuilder())

    # Policy engine + model registry (optional; degrades to None)
    engine = None
    if _HAVE_POLICY:
        try:
            registry = ModelRegistry()
            # register the active LLM's catalog so the policy engine can decide
            registry.register_source(llm)
            engine = PolicyEngine(registry=registry)
        except Exception:
            engine = None
    c.register_instance("PolicyEngine", engine)

    # Router (Wave 6): policy engine + adapter map. Mock is ALWAYS present as
    # the offline fallback entry, even when OmniRoute is the primary.
    adapters_map: Dict[str, ILlm] = {"mock": MockLlmAdapter()}
    if not isinstance(llm, MockLlmAdapter):
        adapters_map["omniroute"] = llm
    router = Router(engine, adapters_map)
    c.register_instance("Router", router)

    # Router port used by the executor: a callable (ModelQuery) -> LlmResponse
    def router_fn(q: ModelQuery) -> LlmResponse:
        return router.route(q)

    # Workflow platform (Wave 10) — composition root wires reflection/retry
    executor: IExecutor = build_executor()
    planner: IPlanner = RuleBasedPlanner()
    c.register_instance("Planner", planner)
    c.register_instance("Executor", executor)

    # Memory platform (Wave 9)
    memory_store = InMemoryMemoryStore()
    memory = MemoryPlatform(memory_store)
    c.register_instance("MemoryStore", memory_store)
    c.register_instance("MemoryPlatform", memory)

    # Knowledge platform (Wave 8) — best-effort; degrade to None if it needs deps
    knowledge = None
    try:
        knowledge = KnowledgePlatform()
    except Exception:
        knowledge = None
    c.register_instance("KnowledgePlatform", knowledge)

    # Learning store (Wave 12) — source of traces for Wave 14 retrospective
    learning_store = InMemoryLearningStore(memory_store)
    c.register_instance("LearningStore", learning_store)

    # Optimization (Wave 13) — PatternBasedOptimizer proposes; ConfigApplier applies
    optimizer = PatternBasedOptimizer()
    c.register_instance("Optimizer", optimizer)

    # Autonomy (Wave 14)
    autonomy = ThresholdAutonomyController(min_traces=1, min_interval_s=0) if cfg["runtime"].get("enable_autonomy", True) else None
    self_evaluator = SimpleSelfEvaluator()
    c.register_instance("AutonomyController", autonomy)
    c.register_instance("SelfEvaluator", self_evaluator)

    # Agent platform (Wave 11) — the orchestrator tying it all together
    session_id = cfg["runtime"].get("session_id") or f"agent:{os.urandom(4).hex()}"
    agent = AgentPlatform(
        planner=planner,
        executor=executor,
        router=router_fn,
        memory=memory,
        knowledge=knowledge,
        evaluator=None,            # Wave 7 evaluator optional at boot
        tools=None,
        policy_engine=engine,
        learning_store=learning_store,
        optimizer=optimizer,
        autonomy_controller=autonomy,
        self_evaluator=self_evaluator,
        session_id=session_id,
    )
    c.register_instance("AgentPlatform", agent)
    c.register_instance("IAgent", agent)  # alias for callers wanting the port
    return c


class Runtime:
    """Unified Runtime Lifecycle (spec diagram: Start Runtime)."""

    def __init__(self, container: DependencyContainer, cfg: Dict[str, Any]) -> None:
        self._c = container
        self._cfg = cfg
        self._services: Dict[str, Any] = {}
        self._running = False

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> "Runtime":
        print("Kernel started")
        # Platforms initialized (all already built in the container)
        print("Platforms initialized")
        print("Router initialized")
        llm = self._c.resolve("LLM")
        kind = "OmniRoute" if not isinstance(llm, MockLlmAdapter) else "Mock"
        print(f"LLM initialized ({kind})")
        # S4: register legacy VaultCrawler as a platform service (no separate launch)
        self._register_legacy_services()
        self._running = True
        print("Runtime ready")
        return self

    def stop(self) -> None:
        self._running = False
        print("Runtime stopped")

    @property
    def running(self) -> bool:
        return self._running

    # --- accessors ---------------------------------------------------------
    @property
    def agent(self) -> AgentPlatform:
        return self._c.resolve("AgentPlatform")

    @property
    def container(self) -> DependencyContainer:
        return self._c

    # --- S4: legacy migration (one module at a time, no rewrite) -----------
    def _register_legacy_services(self) -> None:
        """Mount legacy VaultCrawler as a platform service inside the Runtime.

        We do NOT rewrite the crawler; we make it available through the
        container so future platform calls can delegate to it. If the legacy
        module is unavailable, we skip silently (degraded mode).
        """
        vault_path = self._cfg["runtime"].get("vault_path")
        if not vault_path:
            return
        try:
            from services import VaultStreamCrawler  # legacy composition-root import
            crawler = VaultStreamCrawler(
                self._c.resolve("IFileSystem"),
                self._c.resolve("IEventBus"),
                self._c.resolve("IGraphBuilder"),
                vault_path,
            )
            self._services["vault_crawler"] = crawler
            self._c.register_instance("VaultCrawler", crawler)
            print("Legacy VaultCrawler registered as platform service")
        except Exception as exc:  # noqa: BLE001
            # Legacy crawler needs its own adapters (LocalFileSystemAdapter etc.);
            # absent those, we simply don't mount it — boot continues.
            print(f"Legacy VaultCrawler not mounted (skipped): {exc}")


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="KROFT_OS bootstrap")
    parser.add_argument("--config", default=None, help="path to bootstrap config (json/yaml)")
    parser.add_argument("--ask", default=None, help="ask the agent a single goal and exit")
    parser.add_argument(
        "--llm", default=None, choices=["omniroute", "mock"],
        help="override llm backend (omniroute|mock)",
    )
    parser.add_argument(
        "--vault", default=None,
        help="vault path to mount the legacy VaultCrawler as a platform service (S4)",
    )
    args = parser.parse_args(argv)

    # 1. Load config
    cfg = load_config(args.config)
    if args.llm:
        cfg["llm"]["backend"] = args.llm
    if args.vault:
        cfg["runtime"]["vault_path"] = args.vault

    # 2. Build DI container + LLM factory
    llm = build_llm_factory(cfg)
    container = build_container(cfg, llm)

    # 3. Start runtime
    runtime = Runtime(container, cfg).start()

    # Optional one-shot ask (S2 helper on CLI)
    if args.ask:
        answer = runtime.agent.ask(args.ask)
        print(f"agent> {answer}")
        runtime.stop()
        return 0

    # Interactive REPL-like loop (keeps the OS "running")
    print("\nKROFT_OS interactive (type a goal, or 'exit'):")
    try:
        while True:
            try:
                goal = input("kroft> ").strip()
            except EOFError:
                break
            if goal in ("exit", "quit"):
                break
            if not goal:
                continue
            print(f"agent> {runtime.agent.ask(goal)}")
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
