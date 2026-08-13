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
import os
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
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
    query: Optional[str] = None  # ТЗ-DAILY-01 / Operator: one-shot query via agent loop (Hermes-desktop tool call)
    agent_runtime: bool = True   # Phase C: AgentRuntime дефолтно подключён к ядру (--no-agent-runtime для legacy path)
    knowledge_snapshot: Optional[str] = None  # ТЗ-KNOWLEDGE-PERSIST-01: JSON snapshot of graph+index (survives restart)
    desktop_opt_in: bool = False    # P.6: explicit opt-in for desktop (click/type/open_app); default-deny
    embedding: str = "none"         # Slice: "none" (keyword fallback) | "auto" (local Ollama /v1/embeddings if reachable)
    knowledge_corpus: Optional[str] = None  # Live KROFT_KNOWLEDGE corpus dir; default off.
                                            # When set, the corpus is ingested lazily on the
                                            # first query (boot stays fast; boot-ingest of a 10k+
                                            # corpus would exceed the 60s budget).

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
        # ТЗ-SLICE5-HYGIENE: high-water mark of outcomes already fed into procedural
        # memory, so each real action is counted EXACTLY once (no N-fold accumulation
        # across ticks). _outcomes itself is left intact for observers/tests.
        self._outcomes_evolved = 0
        from adapters.subprocess_sandbox import SubprocessSandbox
        self._sandbox = SubprocessSandbox()
        self.evolver = SkillEvolver(self._sandbox, self.procedural, min_uses=2, success_threshold=0.8)
        # 2) optional LLM advisor (graceful degradation: None = LLM-free deterministic)
        self.llm: Optional[ILlm] = self._build_llm(self.config.llm)
        # ТЗ-PHASE-M (Task 2): wire the live metrics collector so the kernel's existing
        # RuntimeSupervisor hook (collect->reflect->apply, SOFT-only, O1-guarded) activates.
        # LiveMetricsCollector implements ILiveMetricsCollector; kernel_builder
        # builds LiveRuntimeMetrics + RuntimeSupervisor from it. No kernel change (K5/K6).
        from kernel.observability import LiveMetricsCollector
        self._live_collector = LiveMetricsCollector()
        # Slice: embedding adapter for semantic episodic retrieval (K5 reuse of
        # OllamaEmbeddingAdapter). Resolved from env KROFT_EMBEDDING or config.embedding.
        # "none" -> keyword-overlap fallback (default, network-free). "auto" -> local
        # Ollama/LM Studio /v1/embeddings when reachable; unavailable -> embedding stays
        # None and the kernel falls back to keyword-overlap (graceful degradation).
        embedding_mode = (os.environ.get("KROFT_EMBEDDING")
                          or getattr(self.config, "embedding", "none") or "none")
        embedding_adapter = None
        if embedding_mode == "auto":
            from adapters.ollama_embedding import OllamaEmbeddingAdapter
            embedding_adapter = OllamaEmbeddingAdapter()
        self.embedding_adapter = embedding_adapter  # P1-A: reuse for semantic retrieval
        # 2b) Knowledge index (ContentIndex) — built early so it can be wired into
        # the cognitive kernel when a live corpus is configured (retrieval-augmented
        # reasoning, ТЗ). The KnowledgeEngine is built later (after the graph).
        from services.content_index import ContentIndex
        self.content_index = ContentIndex()
        # 3) kernel (CognitiveKernel) via the shared composition factory
        corpus = getattr(self.config, "knowledge_corpus", None)
        self.bus = build_event_bus()
        self.kernel = build_cognitive_kernel(
            node_id=self.config.node_id, llm_client=self.llm,
            memory=self.memory, procedural=self.procedural,
            live_metrics=self._live_collector, embedding=embedding_adapter,
            knowledge_index=self.content_index if corpus else None,
        )
        # ТЗ-PHASE-N/O: wire a REAL execution backend (IExecutor) so the cognitive loop
        # records REAL success/failure outcomes instead of the proxy-fallback (always
        # success). RealWorldExecutor routes Action.kind -> real backends (file/command)
        # and falls back to the deterministic sim for unknown kinds (ТЗ-EX-01). LLM-free
        # + deterministic (I-09). No kernel change — attach_executor is the existing
        # post-hoc wiring API (K5/K6).
        from composition.real_world_executor import RealWorldExecutor
        # P.6: desktop opt-in is explicit — env KROFT_DESKTOP_OPT_IN=1 OR KroftConfig flag.
        # Default-deny: without it, RealWorldExecutor blocks all screen-automation steps.
        # getattr tolerates non-KroftConfig configs (e.g. SimpleNamespace in legacy tests).
        desktop_opt_in = bool(getattr(self.config, "desktop_opt_in", False)) or \
            os.environ.get("KROFT_DESKTOP_OPT_IN") == "1"
        self.kernel.attach_executor(RealWorldExecutor(desktop_opt_in=desktop_opt_in))
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
        from services.knowledge_engine import build_knowledge_engine
        self.engine = build_knowledge_engine(graph=self.graph, content_index=self.content_index)
        self._corpus_ingested = False  # lazy KROFT_KNOWLEDGE corpus ingest flag
        self.vault_reader = ObsidianVaultReader(self.config.vault)
        # ТЗ-KNOWLEDGE-PERSIST-01: restore prior graph + index BEFORE live ingest,
        # so a cold boot reuses on-disk knowledge (starts "already learned").
        self._snapshot_store = None
        # ТЗ-PHASE-M.6: external configs (e.g. SimpleNamespace in agent tests) may omit
        # knowledge_snapshot; use getattr so run_kroft stays compatible without changing
        # the KroftConfig contract (K5/K6: no new field/adapter).
        _knowledge_snapshot = getattr(self.config, "knowledge_snapshot", None)
        if _knowledge_snapshot:
            from composition.knowledge_persistence import KnowledgeSnapshotStore
            self._snapshot_store = KnowledgeSnapshotStore(_knowledge_snapshot)
            self._restore_graph_and_index()
        self._live_note_count = self._ingest_vault_notes()  # 0 when no vault (graceful)
        self.trust = ReferenceTrustRegistry()
        self._seed_demo_trust()
        # ТЗ-PHASE-E: overlay saved running-trust on top of the demo seed so the
        # system's accumulated experience (per-author trust) survives restart.
        self._restore_trust()
        # ТЗ-PHASE-F: final save happens AFTER demo-seed + procedural restore (below),
        # so the snapshot carries the real learned state, not a pre-seed empty one.
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
        from services.planner_agent import PlannerAgent, PlannerAgentExecutor
        from services.finance_agent import FinanceAgent, FinanceAgentExecutor
        from services.multi_agent_executor import MultiAgentExecutor
        research_agent = ResearchAgent(search=self.search, llm=self.llm, top_k=5)
        architect_agent = ArchitectAgent(search=self.search, llm=self.llm, top_k=5)
        programmer_agent = ProgrammerAgent(search=self.search, llm=self.llm, top_k=5)
        writer_agent = WriterAgent(search=self.search, llm=self.llm, top_k=5)
        planner_agent = PlannerAgent(search=self.search, llm=self.llm, top_k=5)
        finance_agent = FinanceAgent(search=self.search, llm=self.llm, top_k=5)
        self.research_executor = ResearchAgentExecutor(research_agent)
        self.architect_executor = ArchitectAgentExecutor(architect_agent)
        self.programmer_executor = ProgrammerAgentExecutor(programmer_agent)
        self.writer_executor = WriterAgentExecutor(writer_agent)
        self.planner_executor = PlannerAgentExecutor(planner_agent)
        self.finance_executor = FinanceAgentExecutor(finance_agent)
        self.loop_executor = LoopAgentExecutor(
            default_agent_id="agent-loop", llm_client=self.llm, budget=5,
            knowledge_index=self.content_index,
            memory=self.memory,
            embedding=self.embedding_adapter)  # ТЗ-L10.4: reuse SAME EmbeddingAdapter as main kernel (no new subsystem)
        self.agent_executor = MultiAgentExecutor([
            self.research_executor, self.architect_executor, self.programmer_executor,
            self.writer_executor, self.planner_executor, self.finance_executor,
            self.loop_executor,
        ])
        # Phase C (Wave C1/C2/C3/C6): Agent Runtime — дефолтно подключён к ядру
        # (product-mode: больше не опциональный флаг). Routed capabilities всегда идут
        # через AgentRuntime.delegate_step (blackboard + delegation + trust + telemetry + gate).
        # Legacy path (orchestrator.dispatch) доступен только при --no-agent-runtime.
        self.agent_runtime: Any = None
        self.workflow_coordinator: Any = None
        if getattr(self.config, "agent_runtime", True):
            from services.agent_runtime import AgentRuntime
            from services.blackboard import InMemoryBlackboard
            from services.delegation_service import DelegationService
            from services.coordination_strategy import StigmergyStrategy
            from services.workflow_coordinator import WorkflowCoordinator
            from services.approval_gate import ApprovalGate
            from adapters.in_memory_telemetry import InMemoryTelemetrySink as InMemoryTelemetry
            from kernel.identity import ReferenceActionLog
            blackboard = InMemoryBlackboard()
            delegation = DelegationService(max_depth=8)
            # Wave C6: Approval Gate (default-deny semantics).
            # Интерактивный (HITL) approver включается при --interactive (product-mode Флаг 1 C6):
            # предохранитель РЕАЛЬНО спрашивает человека. В demo-режиме (без --interactive)
            # остаётся auto-approve для обратной совместимости CI/boot.
            if getattr(self.config, "interactive", False):
                def _human_approver(req):
                    ans = input(
                        f"[approval] чувствительное действие '{req.capability}' "
                        f"({req.action_id}): одобрить? [y/N] "
                    ).strip().lower()
                    return ans in ("y", "yes", "д", "да")
                _approver = _human_approver
                _ttl = 300.0  # человеку нужно время ответить; иначе default-deny по таймауту
            else:
                _approver = lambda req: True
                _ttl = 5.0
            approval_gate = ApprovalGate(
                approver=_approver,
                action_log=ReferenceActionLog(),
                sensitive_capabilities={"finance", "coding"},
                ttl_sec=_ttl,
            )
            self.agent_runtime = AgentRuntime(
                executor=self.agent_executor,
                blackboard=blackboard,
                delegation=delegation,
                root_capability="research",
                trust_registry=self.trust,
                telemetry=InMemoryTelemetry(),
                approval_gate=approval_gate,
                sensitive_capabilities=("finance", "coding"),
            )
            self.workflow_coordinator = WorkflowCoordinator(
                runtime=self.agent_runtime,
                strategy=StigmergyStrategy(),
                root_capability="research",
            )
        self.orchestrator = build_orchestrator(
            identity_registry=self.identity,
            plugin_registry=ReferencePluginRegistry(),
            trust_registry=self.trust,
            action_log=ReferenceActionLog(),
            agent_executor=self.agent_executor,
            runtime=self.agent_runtime,  # Phase C: ядро использует AgentRuntime как основной agent-dispatch
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
        # ТЗ-PHASE-F: overlay saved skills + procedure stats AFTER the demo seed,
        # so accumulated learning (SkillEvolver outcomes) wins over the demo skill.
        self._restore_procedural()
        # ТЗ-PHASE-G: restore recorded episodes into layered memory (after memory exists)
        self._restore_episodic()
        # ТЗ-PHASE-H: restore semantic facts + normative policies into layered memory
        self._restore_semantic()
        self._restore_normative()
        # re-persist after demo-skill seed so the snapshot carries the seeded skill too
        self._save_knowledge()

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

    # ---- Live KROFT_KNOWLEDGE corpus (ТЗ-KNOWLEDGE-LIVE): retrieval-augmented reasoning ----
    def _ingest_corpus(self, path: Optional[str]) -> int:
        """Ingest the atomic Q&A corpus (KROFT_KNOWLEDGE) via the existing
        KnowledgeEngine (reuses graph + ContentIndex; no new storage layer).

        Graceful: missing/empty path -> 0 nodes. Idempotent: a second call is a
        no-op because _corpus_ingested guards it. Returns the ingested node count.
        """
        if not path or not os.path.isdir(path):
            return 0
        count = 0
        for f in sorted(os.listdir(path)):
            if not (f.startswith("qa_") and f.endswith(".md")):
                continue
            doc_id = f[:-3]
            full = os.path.join(path, f)
            try:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
                self.engine.ingest(doc_id, text)
                count += 1
            except Exception:
                continue  # one bad file must not abort the corpus ingest
        self._corpus_ingested = True
        return count

    def query(self, question: str) -> "dict":
        """Retrieval-augmented answer over the live KROFT_KNOWLEDGE corpus.

        The corpus is ingested lazily on the first query (boot stays fast even
        for a 10k+ corpus). Returns a dict with the top-3 node ids and the
        leading citation (node_id) so callers can attribute the answer.
        """
        corpus = getattr(self.config, "knowledge_corpus", None)
        if corpus and not self._corpus_ingested:
            self._ingest_corpus(corpus)
        top = self.content_index.search(question)
        top3 = list(top[:3])
        return {
            "question": question,
            "top3": top3,
            "citation": top3[0] if top3 else None,
        }

    # ---- ТЗ-KNOWLEDGE-PERSIST-01 + ТЗ-PHASE-E: snapshot persistence of live knowledge ----
    def _restore_graph_and_index(self) -> None:
        """Load graph + content index from disk (graceful: missing -> no-op)."""
        if self._snapshot_store is None:
            return
        data = self._snapshot_store.load()
        if not data:
            return  # first run or corrupt snapshot -> build from vault only
        try:
            self.graph.restore(data.get("graph", {}))
        except Exception:
            pass  # a broken graph blob must not abort boot; live ingest still runs
        try:
            self.engine._content_index.restore(data.get("index", {}))
        except Exception:
            pass  # index restore is best-effort; graph + vault reindex cover it

    def _restore_trust(self) -> None:
        """ТЗ-PHASE-E: overlay saved running-trust over the demo seed (graceful)."""
        if self._snapshot_store is None:
            return
        saved = self._snapshot_store.load_trust()
        for author, score in saved.items():
            # reuse the same direct-assignment replay pattern as run_evolution.py
            self.trust._running[author] = float(score)

    def _restore_procedural(self) -> None:
        """ТЗ-PHASE-F: overlay saved skills + procedure stats over the demo seed."""
        if self._snapshot_store is None:
            return
        saved = self._snapshot_store.load_procedural()
        if not saved:
            return
        # procedure usage stats (runs/successes/success_rate) — plain dict replay
        for name, entry in saved.get("procedures", {}).items():
            if isinstance(entry, dict) and "runs" in entry and "successes" in entry:
                self.procedural._procedures[name] = dict(entry)
        # skills (Procedure VO) — reuse the EXISTING converter (K5, no duplicate),
        # then re-attach version + lifecycle that _procedure_from_dict drops (it
        # only maps the base fields). dataclasses.replace keeps it axis-clean.
        from dataclasses import replace
        from kernel.persistence import _procedure_from_dict
        from contracts.i_memory import PolicyLifecycle
        for cap, sk in saved.get("skills", {}).items():
            try:
                proc = _procedure_from_dict(sk)
                proc = replace(
                    proc,
                    version=int(sk.get("version", proc.version)),
                    lifecycle=PolicyLifecycle[sk.get("lifecycle", "ACTIVE")],
                )
                self.procedural._skills[cap] = proc
            except Exception:
                pass  # a malformed skill blob must not abort boot

    def _restore_episodic(self) -> None:
        """ТЗ-PHASE-G: restore recorded Episode list into layered memory."""
        if self._snapshot_store is None:
            return
        saved = self._snapshot_store.load_episodic()
        if not saved:
            return
        # reuse the EXISTING converter (K5, no new serializer)
        from kernel.persistence import _episode_from_dict
        restored = []
        for blob in saved:
            try:
                restored.append(_episode_from_dict(blob))
            except Exception:
                pass  # a malformed episode blob must not abort boot
        # episodes are append-only experience; restore the full prior list
        self.memory._episodes = restored

    def _restore_semantic(self) -> None:
        """ТЗ-PHASE-H: restore consolidated SemanticFacts into layered memory."""
        if self._snapshot_store is None:
            return
        saved = self._snapshot_store.load_semantic()
        if not saved:
            return
        from kernel.persistence import _semantic_from_dict  # reuse existing (K5)
        restored = []
        for blob in saved:
            try:
                restored.append(_semantic_from_dict(blob))
            except Exception:
                pass  # a malformed fact blob must not abort boot
        self.memory._semantic = restored

    def _restore_normative(self) -> None:
        """ТЗ-PHASE-H: restore normative/soft Policies into layered memory."""
        if self._snapshot_store is None:
            return
        saved = self._snapshot_store.load_normative()
        if not saved:
            return
        from kernel.persistence import _policy_from_dict  # reuse existing (K5)
        restored = []
        for blob in saved:
            try:
                restored.append(_policy_from_dict(blob))
            except Exception:
                pass  # a malformed policy blob must not abort boot
        self.memory._normative = restored

    def _save_knowledge(self) -> None:
        """Persist graph + content index + running-trust + procedural + episodes to disk."""
        if self._snapshot_store is None:
            return
        from kernel.persistence import _episode_to_dict  # reuse existing serializer (K5)
        from kernel.persistence import _semantic_to_dict  # reuse existing (K5)
        from kernel.persistence import _policy_to_dict  # reuse existing (K5)
        try:
            meta = {
                "vault": self.config.vault,
                "node_count": len(self.graph.nodes()),
                "edge_count": len(self.graph.edges()),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self._snapshot_store.save(
                self.graph.snapshot(),
                self.engine._content_index.snapshot(),
                meta,
                trust=self.trust._running,
                procedural={
                    "procedures": {k: dict(v) for k, v in self.procedural._procedures.items()},
                    "skills": {
                        cap: {
                            "skill_id": s.skill_id, "name": s.name,
                            "capability": s.capability, "steps": list(s.steps),
                            "preconditions": list(s.preconditions),
                            "confidence": s.confidence, "provenance": s.provenance,
                            "causal": s.causal, "version": s.version,
                            "lifecycle": s.lifecycle.name,
                        }
                        for cap, s in self.procedural._skills.items()
                    },
                },
                episodes=[_episode_to_dict(e) for e in self.memory._episodes],
                semantic=[_semantic_to_dict(f) for f in self.memory._semantic],
                normative=[_policy_to_dict(p) for p in self.memory._normative],
            )
        except Exception:
            pass  # persistence failure must never crash the agent loop

    def _seed_demo_trust(self) -> None:
        for aid in ["agent.research", "agent.architect", "agent.programmer",
                    "agent.writer", "agent.finance", "agent.sales"]:
            self.trust.seed(aid, 0.97)

    def _build_llm(self, mode: str) -> Optional[ILlm]:
        if mode == "none":
            return None  # LLM-free deterministic run (I-09)
        if mode == "mock":
            return _MockLlm()
        if mode == "omniroute":
            # External OmniRoute AI gateway (ТЗ-OMNI-01, ADR-089). Reuses the
            # existing OpenAiCompatibleClient via the factory alias — no new port
            # or adapter. Combo routing + quota-aware fallback live in OmniRoute.
            from composition.llm_client_factory import build_omniroute_client
            try:
                return build_omniroute_client()
            except Exception:
                return None
        # "auto": build a real client. Opt-in OmniRoute via KROFT_LLM_BASE_URL (ТЗ-OMNI-01, ADR-089).
        # Без переменной — прежний путь (одиночный Ollama-клиент localhost:11434/v1), дефолт НЕ меняем.
        # С переменной — строим OmniRouter из одного ProviderSpec (keyless), graceful к retrieval-only.
        from composition.llm_client_factory import build_llm_client
        from contracts.i_model_router import ProviderSpec
        base_url = os.environ.get("KROFT_LLM_BASE_URL")
        model = os.environ.get("KROFT_LLM_MODEL")  # None -> дефолт factory (Ollama "auto")
        # Таймаут 120s: холодная загрузка локальной модели (qwen3.5:9b ~6.5GB) превышает дефолт 30s.
        timeout = float(os.environ.get("KROFT_LLM_TIMEOUT", "120"))
        if not base_url:
            # Дефолтный Ollama-путь. model из KROFT_LLM_MODEL (если задана), иначе auto.
            try:
                if model:
                    return build_llm_client(model=model, timeout=timeout)
                return build_llm_client(timeout=timeout)
            except Exception:
                return None
        spec = ProviderSpec(
            name="omni",
            base_url=base_url,
            api_key_env="",           # keyless gateway
            priority=10,              # первым в цепочке
            model=os.environ.get("KROFT_LLM_MODEL", "auto"),
        )
        try:
            return build_llm_client(providers=[spec], timeout=timeout)
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
        # Lazy-ingest the live KROFT_KNOWLEDGE corpus (if configured) so the wired
        # knowledge index is populated before the tick's retrieval-augmented reasoning
        # queries it (ТЗ: knowledge_index wired into the kernel on corpus config).
        corpus = getattr(self.config, "knowledge_corpus", None)
        if corpus and not self._corpus_ingested:
            self._ingest_corpus(corpus)
        self.kernel.tick(Intent(id="intent-1", text=goal_text, confidence=ConfidenceScore(0.8),
                                provenance=Provenance(source="demo", actor="run_kroft")))
        # ТЗ-PHASE-L: evolve procedural memory from REAL tick outcomes (not fake stats).
        # CognitiveKernel already accumulated ExecutionOutcome(s) this tick in
        # self.kernel._outcomes; SkillEvolver (composition-owned) proposes a better variant
        # when success_rate is low. No kernel change — data is available post-tick (K5/K6).
        self._evolve_procedural_from_runtime()
        self.logs.append(f"tick: kernel={self.kernel._state.name} evolved demo skill")
        # ТЗ-PHASE-K: close the persistence loop — a tick evolves memory (episodes /
        # semantic / normative via CognitiveKernel), so persist it immediately. Without
        # this, run_demo/step develops memory that is lost on restart until a query saves.
        self._save_knowledge()
        return self.dashboard.snapshot()

    def _resolve_skill_from_plan(self):
        """ТЗ-PHASE-M (Task 1): map the last executed Plan to a real Procedure (skill).

        The CognitiveKernel does NOT tag plans with a skill_id (K6: no kernel change),
        but both Plan.steps and Procedure.steps are Tuple[str]. We match the last tick's
        selected plan steps against stored Procedures (exact, then normalized join) and
        return (capability, Procedure). Falls back to the demo skill when no match — so
        the loop always has a skill to evolve. Composition-only (K5/K6).
        """
        plan = getattr(self.kernel, "_last_selected_plan", None)
        if plan is None:
            return "demo", self._demo_skill
        plan_steps = tuple(str(s) for s in getattr(plan, "steps", ()))
        # ТЗ-PHASE-P.6-followup: when the planner emitted structured execution intent,
        # derive the skill capability from the REAL action kind so learning/reuse is
        # keyed by what was actually executed (file/command/desktop), not by the
        # textual plan steps. Reuses Plan.execution_steps (P.1); composition-only (K5/K6).
        exec_steps = getattr(plan, "execution_steps", None)
        if exec_steps:
            first_kind = (exec_steps[0] or {}).get("kind") if exec_steps else None
            if first_kind:
                return f"exec:{first_kind}", self._demo_skill
        if not plan_steps:
            return "demo", self._demo_skill
        # exact steps match
        for cap, proc in self.procedural._skills.items():
            if tuple(str(s) for s in proc.steps) == plan_steps:
                return cap, proc
        # normalized join match (order-insensitive-ish, cheap heuristic)
        joined = "|".join(plan_steps)
        for cap, proc in self.procedural._skills.items():
            if "|".join(str(s) for s in proc.steps) == joined:
                return cap, proc
        return "demo", self._demo_skill

    def _evolve_procedural_from_runtime(self) -> None:
        """ТЗ-PHASE-L/M: feed REAL tick outcomes into SkillEvolver for the executed skill.

        Resolves the skill actually executed this tick (ТЗ-PHASE-M _resolve_skill_from_plan),
        aggregates CognitiveKernel._outcomes (success/utility) into SkillUsageStats, and
        evolves the matching skill when the success rate is low. Reuses SkillEvolver +
        InMemoryProceduralMemory + KnowledgeSnapshotStore; no new port/layer/DTO (K5/K6).
        """
        from contracts.i_skill_evolver import SkillUsageStats
        kout = getattr(self.kernel, "_outcomes", None)
        if not isinstance(kout, list):
            return
        # ТЗ-SLICE6: bound _outcomes growth to a recent window so observers see a bounded
        # list; shift the consumed watermark accordingly. Done BEFORE snapshotting.
        _OUTCOMES_LIMIT = 64
        if len(kout) > _OUTCOMES_LIMIT:
            trimmed = len(kout) - _OUTCOMES_LIMIT
            kout[:] = kout[trimmed:]
            self._outcomes_evolved = max(0, self._outcomes_evolved - trimmed)
        all_outcomes = list(kout)
        # ТЗ-SLICE5-HYGIENE: count each real action EXACTLY once. _procedures['runs'] is
        # incremented only by the NEW outcomes since the last evolve (single-write); the
        # SkillEvolver gate still receives CUMULATIVE uses (so min_uses thresholds fire).
        # _outcomes itself is left intact for observers/tests.
        if len(all_outcomes) < self._outcomes_evolved:
            self._outcomes_evolved = 0
        new_outcomes = all_outcomes[self._outcomes_evolved:]
        if not new_outcomes:
            return
        self._outcomes_evolved += len(new_outcomes)
        capability, skill = self._resolve_skill_from_plan()
        # single-write accumulation for the procedural record
        new_uses = len(new_outcomes)
        new_successes = sum(1 for o in new_outcomes if getattr(o, "success", False))
        # cumulative stats for the SkillEvolver gate (min_uses / success_threshold)
        total_uses = len(all_outcomes)
        total_successes = sum(1 for o in all_outcomes if getattr(o, "success", False))
        success_rate = total_successes / total_uses if total_uses else 0.0
        # accumulate into the per-skill procedure stats so persistence carries the record
        if capability not in self.procedural._procedures:
            self.procedural._procedures[capability] = {
                "capability": capability, "runs": 0, "successes": 0,
            }
        rec = self.procedural._procedures[capability]
        rec["runs"] = int(rec.get("runs", 0)) + new_uses
        rec["successes"] = int(rec.get("successes", 0)) + new_successes
        rec["success_rate"] = (rec["successes"] / rec["runs"]) if rec["runs"] else 0.0
        try:
            evolved = self.evolver.evolve_skill(
                skill, SkillUsageStats(capability=capability, uses=total_uses,
                                       success_rate=success_rate)
            )
            if evolved is not None and evolved is not skill:
                self.procedural.store_skill(evolved)
                self.logs.append(f"procedural evolution: {capability} -> v{evolved.version}")
        except Exception:
            pass  # evolution must never break the runtime loop

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
        # Agents v0.1: route recognised agent intents.
        capability = self._route_capability(query)
        # Phase C (Wave C6): routed-capability делегируется через AgentRuntime.delegate_step
        # (консультирует Approval Gate для sensitive capabilities). При --no-agent-runtime
        # self.agent_runtime is None -> legacy orchestrator.dispatch ниже.
        if capability is not None and getattr(self, "agent_runtime", None) is not None:
            goal = OrchestrationGoal(goal_id=task_id, capability=capability, payload=query)
            outcome = self.agent_runtime.delegate_step(task_id, goal)
            self.task_store.update(task_id, "done" if outcome.success else "failed")
            return outcome.detail if outcome.success else f"[no answer] {outcome.detail}"
        if capability is not None and getattr(self, "agent_executor", None) is not None \
                and capability in self.agent_executor._by_capability:
            goal = OrchestrationGoal(goal_id=task_id, capability=capability, payload=query)
            outcome = self.orchestrator.dispatch(goal)
            self.task_store.update(task_id, "done" if outcome.success else "failed")
            if outcome.success:
                return outcome.detail
            return f"[no answer] {outcome.detail}"
        # Phase C (Wave C2): если --agent-runtime вкл — маршрут через WorkflowCoordinator
        # (build_workflow -> stigmergy run через AgentRuntime). Без флага — legacy path ниже.
        if getattr(self, "workflow_coordinator", None) is not None:
            wf = self.workflow_coordinator.build_workflow(query)
            wf = self.workflow_coordinator.run(wf)
            self.task_store.update(task_id, "done" if wf.status == "done" else "failed")
            if wf.status == "done" and wf.plan:
                return wf.plan[0].output
            return f"[no answer] workflow {wf.status}: {wf.plan[0].error if wf.plan else 'empty'}"
        # Backward-compatible path for non-agent intents.
        self.kernel.tick(Intent(id=task_id, text=query, confidence=ConfidenceScore(0.8),
                                provenance=Provenance(source="interactive", actor="user")))
        # ТЗ-PHASE-L: evolve procedural memory from the REAL outcome of this tick.
        self._evolve_procedural_from_runtime()
        self.task_store.update(task_id, "done")
        # answer from the live graph (real vault content)
        hits = self.search.search(query, top_k=5)
        if not hits:
            return f"[no hits] query processed (task {task_id}); vault has no match for: {query}"
        lines = [f"[answer] {h.source} (conf={h.confidence.value:.2f}, rel={h.relevance})"
                 for h in hits]
        self._save_knowledge()  # ТЗ-KNOWLEDGE-PERSIST-01: persist after each query
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
        if any(tok in q for tok in ("plan", "roadmap", "milestone", "sprint", "timeline",
                                     "task breakdown", "planning", "schedule")):
            return "planning"
        if any(tok in q for tok in ("finance", "trading", "market", "portfolio", "risk",
                                     "invest", "crypto", "stock", "budget")):
            return "finance"
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
    p.add_argument("--agent-runtime", dest="agent_runtime", action="store_true", default=True,
                   help="Phase C: AgentRuntime дефолтно подключён к ядру (routed capabilities "
                        "идут через runtime+gate). Включено по умолчанию.")
    p.add_argument("--no-agent-runtime", dest="agent_runtime", action="store_false",
                   help="Отключить AgentRuntime: routed capabilities идут через legacy "
                        "orchestrator.dispatch (без blackboard/delegation/gate).")
    p.add_argument("--vault", default=None, help="Obsidian vault path for live note ingestion (ТЗ-DAILY-01)")
    p.add_argument("--knowledge-snapshot", default=None,
                   help="ТЗ-KNOWLEDGE-PERSIST-01: JSON file to persist/restore the live "
                        "knowledge graph + index across restarts (so KROFT_OS starts learned)")
    p.add_argument("--interactive", action="store_true",
                   help="ТЗ-DAILY-01: read queries from stdin -> agent loop -> live answer")
    p.add_argument("--query", default=None,
                   help="ТЗ-DAILY-01 / Operator: one-shot query -> agent loop -> print answer -> exit "
                        "(no stdin). Используется Hermes-desktop для вызова KROFT_OS как инструмента.")
    a = p.parse_args(argv)
    return KroftConfig(
        node_id=a.node_id, llm=a.llm, federation=a.federation,
        ticks=a.ticks, run_demo=not a.no_demo, vault=a.vault, interactive=a.interactive,
        agent_runtime=a.agent_runtime, query=a.query,
        knowledge_snapshot=a.knowledge_snapshot,
    )


def main(argv: Optional[List[str]] = None) -> int:
    config = _parse_args(argv)
    app = KroftApp(config)
    if config.interactive:
        app.run_interactive()
    elif config.query:
        print(app.interactive_query(config.query))
    elif config.run_demo:
        app.run_demo()
    else:
        print(f"[run_kroft] booted node={config.node_id} (no-demo); services ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
