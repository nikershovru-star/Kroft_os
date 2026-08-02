# Releases

> Lightweight changelog for KROFT_OS. Detailed history lives in repo CHANGELOG.md.

## [Unreleased]
- Rebrand: KnowledgeOS v5 → **KROFT_OS** (Autonomous Intelligence Operating System).
- Unified ADR numbering: `docs/architecture/ADR-001…` (was ad-hoc ADR-033/034).
- Model Platform vertical closed (ADR-006): ILlm + OmniRoute/Ollama adapters + ModelRegistry + Wave 6 gateway-truth routing.
- Policy Platform closed (ADR-009, Wave 5/5.1/5.2): PolicyEngine + Budget/Privacy/Security/ProviderSelection.
- Evaluation Platform closed (ADR-010, Wave 7): MetricsCollector, BenchmarkRunner, Golden Dataset, scorecard-blended routing.
- **Knowledge Platform closed (ADR-011, Wave 8):** `IEntityExtractor`/`IValidator`/`IFactChecker`/`IKnowledgeGraph`
  ports, frozen `Fact` with append-only history, `LLMEntityExtractor` (Router-driven), `GraphKnowledgeStore`
  over the existing `InMemoryGraphBuilder`, `KnowledgePlatform` orchestrator with a 0.7 confidence gate.
  Rule enforced: *LLM produces hypotheses; the graph stores only verified facts.*
  Commits `ca32626`, `ba38ee4`, `cf453cd`.
- **Workflow Platform closed (ADR-013, Wave 10):** `IPlanner`/`IExecutor`/`IReflection`/`IRetryManager`
  ports, frozen `Workflow`/`Step` with copy-on-write transitions, JSON round-trip DoD (no time
  fields — reproducibility is byte-stable). `RuleBasedPlanner` (keyword → ordered template,
  first-match-wins). `WorkflowExecutor` over real `StepReflection` + `RetryManager` (attempt 2 →
  `reasoning=True`, attempt 3 → `local=True`, route change not repeat). `workflow_runner` is the
  composition root so the executor imports only contracts. Commits `565e4f4`, `4f8fc1b`,
  `7e5c2ad`, `01780c9`.
- **Memory Platform closed (ADR-012, Wave 9):** `IMemoryStore`/`ISemanticMemory`/`IProceduralMemory`
  ports, frozen `MemoryItem` with tuple-normalised tags, lazy TTL + measured compression,
  `InMemoryMemoryStore`, keyword `SemanticMemoryStub` (reads Wave 8 graph facts through an
  injected callable — no service import), `MemoryPlatform` with Session→prompt augmentation and
  explained Session→Long-Term consolidation. Five memory types are tag-based roles over one port,
  not five interfaces. Commits `ce26ac2`, `47a8a1f`, `fee3086`.
- **Agent Platform closed (ADR-014, Wave 11):** `IAgentPlatform` + frozen `AgentResult`
  (copy-on-write, no time fields — reproducibility). `AgentPlatform` orchestrator injects
  Planner (Wave 10) + Executor (Wave 10) + optional Memory/Knowledge/Eval/Tools; depends ONLY on
  `contracts.*` (LAW 2, арх-гейт без новых нарушений). Не переписывает `AgentService` (Stage 33,
  30+ тестов нетронуты) — платформенный слой оркестрации поверх существующего ядра.
  Commits `aa3196d`, `b5f115f`, `a31d6a3`, `ea1de10`. Регресс волн 5–11: **161 passed, 8 skipped**.
- **Learning Platform closed (ADR-015, Wave 12):** `ILearningStore`/`IPatternExtractor` ports,
  frozen `ExecutionTrace`/`StepTrace`/`Pattern` (append-only history), `InMemoryLearningStore`,
  `RuleBasedPatternExtractor` (keyword → pattern, first-match-wins). `AgentPlatform._record_trace`
  builds an immutable trace from a completed run. Commits `610b628`, `b2e6801`, `aa63912`, `a46efa2`.
- **Optimization Platform closed (ADR-016, Wave 13):** `IOptimizer`/`IGuardrail` ports, frozen
  `Recommendation` (confidence-gated), `ConfigApplier` — the ONLY runtime mutation point
  (propose → approve → apply → rollback, two-phase commit). `PatternBasedOptimizer` + `SimpleGuardrail`.
  Invariant: optimizers only PROPOSE; apply requires human approve. Commits `05c6b04`, `23ae648`,
  `e119e2a`, `a02979d`.
- **Autonomous Hermes closed (ADR-017, Wave 14):** `IAutonomyController`/`ISelfEvaluator`/`IDocMaintainer`
  ports + frozen `EvaluationReport`/`DocSyncResult`. `ThresholdAutonomyController` (rate-limited
  self-initiated retrospective), `SimpleSelfEvaluator` (metrics from real Wave 12 fields),
  `StaticDocMaintainer` (read-only doc/code check), `LlmOptimizer` (2nd `IOptimizer`, LLM-backed,
  whitelist + confidence gate). `AgentResult.autonomy_log` (observe-only). Invariant: **no Wave 14
  component calls `ConfigApplier.apply()` directly** — mutation stays in Wave 13.
  Commits `66a1764`, `ff89237`, `42d6020`, `427f3f0`.
- **Debt Triage (post-Wave 14, separate track):** arch-gate (`tests/test_architecture.py`) was red on
  pre-existing LAW 2 violations. Fixed minimally & reversibly: `services/workflow_runner.py` +
  `adapters/router.py` → lazy `importlib` (no top-level sibling imports); `services/llm_optimizer.py`
  → `fallback` injected (no `services` import). Arch-gate now **3 passed (0 violations)**. Wave 13
  test assertions fixed (float tolerance, `applied`-status, scalar value). Commits `bf0315e`, `12eea22`.

## [v1.0] — 2026-07-31 — All 14 waves shipped

**Status:** KROFT_OS poligon (`KnowledgeOS-v5`) complete. All 14 waves of the Master
Architecture Roadmap are CLOSED. The dependency-axis architecture gate is fully green
(0 forbidden cross-layer imports). Regression across waves 5–14: **225 passed / 10 skipped**.

**What was built (summary):**
- Foundation: kernel event bus, observability, contracts (Wave 0–2).
- Resource platforms: Model/OmniRoute (ADR-006), Registry (Wave 4), Policy (ADR-009),
  Routing (Wave 6).
- Cognitive platforms: Evaluation (ADR-010), Knowledge (ADR-011), Memory (ADR-012),
  Workflow (ADR-013), Agent (ADR-014), Learning (ADR-015), Optimization (ADR-016),
  Autonomous Hermes (ADR-017).
- The observe → learn → optimize → act loop is closed: agents run (Wave 11), record
  immutable traces (Wave 12), self-evaluate quality (Wave 14), and propose optimizations
  through guardrailed, human-approved mutation (Wave 13) — with NO autonomous runtime mutation.

**Known residual (out of scope, untouched):** orphaned files `services/agent_service.py`,
`services/graph_query_engine.py`, `stubs/`, `tests/test_graph_*`, `tests/test_semantic_search`
predate the wave structure and are not part of any closed wave. They remain in the repo
unmodified; removing or fixing them requires an explicit separate decision.

## Notes
- Repo folder `KnowledgeOS-v5` still pending OS-level rename to `KROFT_OS` (locked by host).
- `services/session_store.py` (Stage 39/41) remains a parallel legacy session path; migration to
  `IMemoryStore` planned for v0.5.
