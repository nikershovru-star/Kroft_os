"""Bootable KROFT_OS entry point — single command lifts the whole stack (ТЗ-RUN-01, ADR-099, Флаг C).

K5: PURE COMPOSITION over already-shipped components — NO new contract/port. Reuses:
  - build_kernel (composition/kernel_factory.py) — boot the CognitiveKernel.
  - SkillEvolver (EVOLUTION-01) + InMemoryProceduralMemory — self-evolving skills.
  - build_default_dashboard (DESKTOP-01) — read-only kernel-state snapshot + renderer.
  - build_llm_client / OmniRouter (OMNI-01) — optional LLM advisor (graceful degradation).
  - SkillDistributor + SkillRepository + ReferenceTrustRegistry (FED-REPL-01 / IDT-01) — optional
    federation (graceful degradation when disabled).
  - SubprocessSandbox (ADR-039), HmacSigner (CRYPTO-01) — injected dependencies.
Does NOT duplicate run_evolution.py (ТЗ-LIVE-01): that script owns persistence/autosave/live-loop;
this entry point is the higher-level "boot EVERYTHING + show dashboard + demo evolution" aggregator.
run_evolution can be layered on top (it imports the same build_kernel).

Graceful degradation: LLM and federation are OPTIONAL. Without them the app boots and runs a
deterministic, LLM-free evolution demo (I-09). No network or external model required.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from dataclasses import dataclass
from typing import Any, List, Optional

from contracts.cognitive_domain import ConfidenceScore, Intent, Provenance
from contracts.i_identity import AgentIdentity
from contracts.i_llm import ILlm, ModelInfo
from composition.desktop_dashboard_factory import build_default_dashboard
from composition.kernel_factory import build_event_bus
from kernel.cognitive_kernel import build_kernel as build_cognitive_kernel
from kernel.identity import ReferenceIdentityRegistry, ReferenceTrustRegistry
from kernel.memory_store import InMemoryLayeredMemory
from services.knowledge_graph.engine import InMemoryGraphEngine
from services.memory_platform import InMemoryProceduralMemory
from services.obsidian_vault_reader import ObsidianVaultReader
from services.skill_evolution import SkillEvolver
from services.skill_marketplace import SkillRepository
from services.task_store import TaskStore
from contracts.model_registry import ModelRegistry


@dataclass
class KroftConfig:
    """Run configuration for the bootable stack (ТЗ-RUN-01)."""

    node_id: str = "nodeA"
    llm: str = "none"          # "none" (LLM-free deterministic) | "auto" | "mock"
    federation: bool = False    # enable SkillDistributor federation layer
    ticks: int = 5             # demo loop iterations
    run_demo: bool = True      # execute the live-demo loop on __main__
    vault: Optional[str] = None  # Obsidian vault path for live note ingestion (ТЗ-DAILY-01)
    interactive: bool = False    # ТЗ-DAILY-01: read queries from stdin -> agent loop -> answer


class KroftApp:
    """Bootable KROFT_OS: kernel + optional LLM + evolution + optional federation + dashboard.

    Read-only dashboard reflects live state; evolution uses the existing SkillEvolver (LLM-free by
    default). Federation is opt-in (graceful degradation). The app never mutates kernel HARD/FSM via
    the dashboard (DESKTOP-01 read-only contract).
    """

    def __init__(self, config: Optional[KroftConfig] = None) -> None:
        self.config = config or KroftConfig()
        # 1) memory stores: layered (kernel reasoning) + procedural (skills / evolution)
        self.memory = InMemoryLayeredMemory()
        self.procedural = InMemoryProceduralMemory()
        from adapters.subprocess_sandbox import SubprocessSandbox
        self._sandbox = SubprocessSandbox()
        self.evolver = SkillEvolver(self._sandbox, self.procedural, min_uses=2, success_threshold=0.8)
        # 2) optional LLM advisor (graceful degradation: None = LLM-free deterministic)
        self.llm: Optional[ILlm] = self._build_llm(self.config.llm)
        # 3) kernel (CognitiveKernel) via the shared composition factory
        self.bus = build_event_bus()
        self.kernel = build_cognitive_kernel(
            node_id=self.config.node_id, llm_client=self.llm,
            memory=self.memory, procedural=self.procedural,
        )
        # 4) REAL subsystem components (reused, no new port) — feed the dashboard with live numbers
        self.identity = ReferenceIdentityRegistry()
        self._seed_demo_agents()
        self.models = ModelRegistry()
        self._seed_demo_models()
        self.skill_repo = SkillRepository(signer=None)
        self._seed_demo_marketplace()
        self.graph = InMemoryGraphEngine()
        # KnowledgeEngine (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091) — reused, NOT duplicated.
        # Ingests REAL vault notes into the graph so memory_notes becomes a live count.
        from services.content_index import ContentIndex
        from services.knowledge_engine import build_knowledge_engine
        self.engine = build_knowledge_engine(graph=self.graph, content_index=ContentIndex())
        self.vault_reader = ObsidianVaultReader(self.config.vault)
        self._live_note_count = self._ingest_vault_notes()  # 0 when no vault (graceful)
        self.trust = ReferenceTrustRegistry()
        self._seed_demo_trust()
        self.logs: "deque[str]" = deque(maxlen=50)
        self.task_store = TaskStore()  # real component (ТЗ-DAILY-01), empty until agent loop enqueues
        # search over the live knowledge graph (ТЗ-SEARCH-01) — reused for the interactive contour
        from kernel.search import ReferenceSearchService
        self.search = ReferenceSearchService(self.memory, self.graph)
        # 6b) Agents v0.1 (ADR-102, ТЗ-AGENT-BEHAVIOUR-01): wire specialised agents into the
        # existing Orchestrator dispatch path. Each agent reuses the live search service;
        # LLM is optional (graceful, I-09). No new port/layer — composition-only wiring.
        # Multiple agents are composed behind ONE MultiAgentExecutor (services/multi_agent_executor.py),
        # which maps capability -> executor so the single injected IAgentExecutor can drive many.
        from contracts.i_orchestrator import OrchestrationGoal
        from kernel.orchestrator import build_orchestrator
        from kernel.identity import ReferenceActionLog
        from kernel.plugin import ReferencePluginRegistry
        from services.research_agent import ResearchAgent, ResearchAgentExecutor
        from services.architect_agent import ArchitectAgent, ArchitectAgentExecutor
        from services.programmer_agent import ProgrammerAgent, ProgrammerAgentExecutor
        from services.writer_agent import WriterAgent, WriterAgentExecutor
        from services.multi_agent_executor import MultiAgentExecutor
        research_agent = ResearchAgent(search=self.search, llm=self.llm, top_k=5)
        architect_agent = ArchitectAgent(search=self.search, llm=self.llm, top_k=5)
        programmer_agent = ProgrammerAgent(search=self.search, llm=self.llm, top_k=5)
        writer_agent = WriterAgent(search=self.search, llm=self.llm, top_k=5)
        self.research_executor = ResearchAgentExecutor(research_agent)
        self.architect_executor = ArchitectAgentExecutor(architect_agent)
        self.programmer_executor = ProgrammerAgentExecutor(programmer_agent)
        self.writer_executor = WriterAgentExecutor(writer_agent)
        self.agent_executor = MultiAgentExecutor([
            self.research_executor, self.architect_executor, self.programmer_executor,
            self.writer_executor,
        ])
        self.orchestrator = build_orchestrator(
            identity_registry=self.identity,
            plugin_registry=ReferencePluginRegistry(),
            trust_registry=self.trust,
            action_log=ReferenceActionLog(),
            agent_executor=self.agent_executor,
        )
        # 5) optional federation (graceful degradation: disabled by default)
        self.distributor: Any = None
        if self.config.federation:
            self._wire_federation()
        # 6) dashboard (read-only snapshot of the whole stack)
        self.dashboard = build_default_dashboard(
            kernel=self.kernel,
            memory_platform=self.procedural,
            trust_registry=self.trust,
            identity_registry=self.identity,
            model_registry=self.models,
            skill_repository=self.skill_repo,
            distributor=self.distributor,
            graph_engine=self.graph,
            logs_buffer=self.logs,
            task_store=self.task_store,
        )
        self._seed_demo_skill()

    # --- demo seeders (reuse existing component accessors; composition-only scaffolding) ---
    def _seed_demo_agents(self) -> None:
        for aid, spec in [
            ("agent.research", "research"),
            ("agent.architect", "architecture"),
            ("agent.programmer", "coding"),
            ("agent.writer", "writing"),
            ("agent.finance", "finance"),
            ("agent.sales", "sales"),
        ]:
            self.identity.register(AgentIdentity(
                agent_id=aid, specialization=spec, trust_level=0.9))

    def _seed_demo_models(self) -> None:
        for mid in ["qwen3.5", "llama3"]:
            self.models.register_model(ModelInfo(id=mid, provider="local", reasoning=False,
                                                 local=True, free=True, json_mode=True, context_window=32768))

    def _seed_demo_marketplace(self) -> None:
        # seed installed skills so the panel shows a real marketplace count
        for i in range(1, 53):
            self.skill_repo._installed[f"skill.{i}"] = {"name": f"skill.{i}", "version": 1}

    def _ingest_vault_notes(self) -> int:
        """ТЗ-DAILY-01: ingest REAL vault notes via KnowledgeEngine -> graph (live memory_notes).

        Graceful: missing/empty vault -> 0 notes (no crash). Returns the live graph node count.
        """
        notes = self.vault_reader.read_notes()
        for n in notes:
            try:
                self.engine.ingest(n.doc_id, n.text)
            except Exception:
                continue  # a single bad note must not abort the whole ingestion
        return len(self.graph.nodes())

    def _seed_demo_trust(self) -> None:
        for aid in ["agent.research", "agent.architect", "agent.programmer",
                    "agent.writer", "agent.finance", "agent.sales"]:
            self.trust.seed(aid, 0.97)

    def _build_llm(self, mode: str) -> Optional[ILlm]:
        if mode == "none":
            return None  # LLM-free deterministic run (I-09)
        if mode == "mock":
            return _MockLlm()
        # "auto": build a real client (endpoint may be unreachable; we never call it in the demo)
        try:
            from composition.llm_client_factory import build_llm_client
            return build_llm_client()
        except Exception:
            return None

    def _wire_federation(self) -> None:
        from adapters.hmac_signer import HmacSigner
        from infrastructure import InMemoryEventBus
        from services.skill_distributor import SkillDistributor
        from composition.capstone_distributed import LoopbackTransport
        # reuse self.trust (already seeded) + build a federation distributor over the local repo
        signer = HmacSigner(b"kroft-shared-secret")
        fed_repo = SkillRepository(signer=signer)
        # LoopbackTransport expects an InMemoryEventBus with a `members` registry (infrastructure bus).
        fed_bus = InMemoryEventBus()
        if not hasattr(fed_bus, "members"):
            fed_bus.members = []  # duck-typed compat for LoopbackTransport membership check
        self.distributor = SkillDistributor(
            self.config.node_id, fed_repo, LoopbackTransport(fed_bus), self.trust
        )

    def _seed_demo_skill(self) -> None:
        """Seed a low-efficiency skill so the evolution loop has something to improve (deterministic)."""
        from contracts.i_memory import Procedure
        self._demo_skill = Procedure(
            skill_id="demo.v1", name="demo", capability="demo",
            steps=("echo ok", "exit 1 # low-eff step"), version=1, confidence=0.7,
        )
        try:
            self.procedural.store_skill(self._demo_skill)
        except Exception:
            pass

    def step(self, goal_text: str = "demo goal") -> Any:
        """Advance one tick (kernel FSM) + evolve the demo skill; return a read-only dashboard snapshot."""
        from contracts.cognitive_domain import ConfidenceScore, Provenance
        self.kernel.tick(Intent(id="intent-1", text=goal_text, confidence=ConfidenceScore(0.8),
                                provenance=Provenance(source="demo", actor="run_kroft")))
        # Evolution: low-efficiency usage stats -> SkillEvolver proposes a better variant (LLM-free)
        from contracts.i_skill_evolver import SkillUsageStats
        self.evolver.evolve_skill(
            self._demo_skill, SkillUsageStats(capability="demo", uses=10, success_rate=0.3)
        )
        self.logs.append(f"tick: kernel={self.kernel._state.name} evolved demo skill")
        return self.dashboard.snapshot()

    def run_demo(self, ticks: Optional[int] = None) -> List[Any]:
        """Live-demo loop: tick + evolve, printing a read-only dashboard snapshot each iteration.

        Deterministic without an LLM (I-09); evolution uses the LLM-free SkillEvolver heuristic.
        """
        ticks = ticks if ticks is not None else self.config.ticks
        snaps: List[Any] = []
        print(f"[run_kroft] booting node={self.config.node_id} "
              f"(llm={self.config.llm}, federation={self.config.federation})")
        for i in range(max(0, ticks)):
            snap = self.step()
            snaps.append(snap)
            print(f"\n=== tick {i + 1}/{ticks} ===")
            print(self.dashboard.render_text(snap))
        print(f"\n[run_kroft] demo complete: {ticks} ticks, "
              f"skills in memory={self.dashboard.render_json(snaps[-1]) is not None}")
        return snaps

    def interactive_query(self, query: str) -> str:
        """ТЗ-DAILY-01: minimal interactive contour + Agents v0.1 (ADR-102).

        Agent intents (research / architecture / ...) are routed through the REAL
        Orchestrator.dispatch -> specialised agent (Goal -> Orchestrator -> Agent ->
        KnowledgeEngine/ReferenceSearchService -> AgentResult). Other intents keep the
        original kernel-tick + live-search path (backward compatible). Deterministic;
        LLM-free by default (I-09).
        """
        from contracts.cognitive_domain import ConfidenceScore, Provenance
        from contracts.i_orchestrator import OrchestrationGoal
        task_id = f"task-{len(self.task_store.list()) + 1}"
        self.task_store.add(task_id, "running")
        # Agents v0.1: route recognised agent intents through the agent dispatch path.
        capability = self._route_capability(query)
        if capability is not None and getattr(self, "agent_executor", None) is not None \
                and capability in self.agent_executor._by_capability:
            goal = OrchestrationGoal(goal_id=task_id, capability=capability, payload=query)
            outcome = self.orchestrator.dispatch(goal)
            self.task_store.update(task_id, "done" if outcome.success else "failed")
            if outcome.success:
                return outcome.detail
            return f"[no answer] {outcome.detail}"
        # Backward-compatible path for non-agent intents.
        self.kernel.tick(Intent(id=task_id, text=query, confidence=ConfidenceScore(0.8),
                                provenance=Provenance(source="interactive", actor="user")))
        self.task_store.update(task_id, "done")
        # answer from the live graph (real vault content)
        hits = self.search.search(query, top_k=5)
        if not hits:
            return f"[no hits] query processed (task {task_id}); vault has no match for: {query}"
        lines = [f"[answer] {h.source} (conf={h.confidence.value:.2f}, rel={h.relevance})"
                 for h in hits]
        return "\n".join(lines)

    @staticmethod
    def _route_capability(query: str) -> Optional[str]:
        """Map a free-text query to a wired agent capability (or None for the legacy path)."""
        from contracts.i_orchestrator import OrchestrationGoal  # noqa: F401 (kept local)
        q = (query or "").lower()
        if any(tok in q for tok in ("adr", "architecture", "architect", "design decision",
                                     "system design", "constitutional")):
            return "architecture"
        if any(tok in q for tok in ("code", "function", "implement", "class", "bug",
                                     "refactor", "programming", "coding", "python")):
            return "coding"
        if any(tok in q for tok in ("write", "document", "draft", "blog", "article",
                                     "summary", "documentation", "writing")):
            return "writing"
        if any(tok in q for tok in ("what is", "what are", "explain", "research", "search",
                                     "find", "how does", "kroft", "agent")):
            return "research"
        return None

    def run_interactive(self) -> None:
        """ТЗ-DAILY-01: read queries from stdin, answer via the agent loop + live search."""
        print(f"[run_kroft] interactive mode (node={self.config.node_id}); type a query, Ctrl-D to exit")
        try:
            while True:
                try:
                    q = input("kroft> ").strip()
                except EOFError:
                    break
                if not q:
                    continue
                print(self.interactive_query(q))
        except KeyboardInterrupt:
            pass
        print("\n[run_kroft] interactive session ended.")


class _MockLlm(ILlm):
    """Deterministic mock ILlm for demo runs (no network)."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return f"[mock] {prompt[:32]}"

    def stream(self, prompt: str, **kwargs: Any):
        yield f"[mock] {prompt[:32]}"


def _parse_args(argv: Optional[List[str]] = None) -> KroftConfig:
    p = argparse.ArgumentParser(description="Bootable KROFT_OS — lift the whole stack + live demo")
    p.add_argument("--node-id", default="nodeA")
    p.add_argument("--llm", choices=["none", "auto", "mock"], default="none")
    p.add_argument("--federation", action="store_true", help="enable SkillDistributor federation layer")
    p.add_argument("--ticks", type=int, default=5)
    p.add_argument("--no-demo", action="store_true", help="boot only, do not run the demo loop")
    p.add_argument("--vault", default=None, help="Obsidian vault path for live note ingestion (ТЗ-DAILY-01)")
    p.add_argument("--interactive", action="store_true",
                   help="ТЗ-DAILY-01: read queries from stdin -> agent loop -> live answer")
    a = p.parse_args(argv)
    return KroftConfig(
        node_id=a.node_id, llm=a.llm, federation=a.federation,
        ticks=a.ticks, run_demo=not a.no_demo, vault=a.vault, interactive=a.interactive,
    )


def main(argv: Optional[List[str]] = None) -> int:
    config = _parse_args(argv)
    app = KroftApp(config)
    if config.interactive:
        app.run_interactive()
    elif config.run_demo:
        app.run_demo()
    else:
        print(f"[run_kroft] booted node={config.node_id} (no-demo); services ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
