---
tags: [kroft, moc, architecture, index]
created: 2026-07-31
status: active
version: 1.0
updated: 2026-07-31
author: Chief Knowledge Architect (Hermes)
summary: >-
  Maps of Content для KROFT_OS: единая точка входа во все инженерные знания —
  ядро, платформы-волны, ADR, спецификации, ревью, roadmap. Каждый документ
  Vault достижим отсюда (KMP v2.0 §14).
related:
  - "ROADMAP.md"
  - "RELEASES.md"
  - "Build Journal — Wave 3-11.md"
  - "Architecture Review v1.0.md"
---

# KROFT_OS — Architecture MOC

> **Single Source of Truth** (KMP v2.0). Статус каждого узла — на момент 2026-07-31.
> Если документ недостижим отсюда — он изолирован, что запрещено (KMP §7).

## ⚙️ Иерархия документов KROFT (система координат, НЕ линейная последовательность)

```
KP      (философия/мировоззрение — почти никогда не меняется; РОЖДАЕТ LAW)
 ├── Vision  (стратегия — может меняться)
 │    ├── KERA   (как устроена система — КОНСТИТУЦИЯ, стабильна)
 │    │    └── KERA Views (Logical/Runtime/Deployment/Knowledge/Security/Evolution)
 │    ├── KEH    (как принимаем решения — MOC методологии → Handbook'и)
 │    │    └── KES   (наука доказательств — MOC науки → дисциплины)
 │    ├── KL     (единный словарь — ubiquitous language)
 │    │    └── Glossary (machine-readable версия KL)
 │    ├── RFC    (обсуждаемое предложение — ДО принятия)
 │    ├── AKB    (что знаем — machine-readable данные, растёт)
 │    ├── ADR    (принятое решение — частые, точечные)
 │    ├── Patterns / Standards / Experiments / Benchmarks (artefacts)
 │    └── Runtime (ядро — код, минимален по LAW K3/K8)
```

### Философия и язык (самый верх)
- [[KROFT Philosophy (KP) v1.0]] — МИРОВОЗЗРЕНИЕ. KP-001..007 (Knowledge>Code, Evidence>Opinion, Architecture>Features, Small Kernel, Composable, Humans Approve, Everything Measurable). **Рождает LAW** (не наоборот). Почти никогда не меняется.
- [[KROFT Language (KL) v1.0]] — ЕДИНЫЙ СЛОВАРЬ (ubiquitous language, DDD). Agent/Platform/Kernel/Capability/Research/Evidence/Artifact/Knowledge/Loop/Composition Root/Experiment/Contract/Boundary/Projection/Decision/Signal. Чтобы Agent/Worker/Executor/Service не стали синонимами.
- AKB Glossary: [[docs/architecture/akb/glossary.yaml]] — machine-readable KL (term/definition/aliases/deprecated/introduced/used_in). Проверяется doc-lint.

### Конституция и Views
- [[KROFT Engineering Reference Architecture (KERA) v1.0]] — КОНСТИТУЦИЯ. Mission+boundaries, 3 слоя, EIP (3 контура), 10 платформ (смысловые названия, не P1–P10), зрелость (named stages: Foundation/Operational/Autonomous, не L1–L18 как primary), LAW K1–K8 как lenses, governance.
- [[KERA Views]] — адаптированный 4+1 (Kruchten): [[KERA View — Logical]], [[KERA View — Runtime]], [[KERA View — Deployment]], [[KERA View — Knowledge]], [[KERA View — Security]], [[KERA View — Evolution]]. KERA компактна; Views развиваются отдельно.

### Методология и наука (MOC-навигация, НЕ энциклопедии)
- [[KROFT Engineering Handbook (KEH) v1.0]] — MOC МЕТОДОЛОГИИ → Handbook'и: [[KEH — Research Handbook]], [[KEH — ADR Handbook]], [[KEH — Benchmark Handbook]], [[KEH — Documentation Handbook]], [[KEH — Review Handbook]], [[KEH — Experiment Handbook]].
- [[KROFT Engineering Science (KES) v1.0]] — MOC НАУКИ → дисциплины: [[KES — Research Science]], [[KES — Decision Science]], [[KES — Benchmark Science]], [[KES — Reliability Science]], [[KES — Economics]], [[KES — Human Factors]].

### RFC (обсуждаемое предложение, ДО ADR)
- [[KROFT RFC Layer]] — конвейер Research→Experiment→RFC→ADR→Implementation. RFC = discussion, ADR = decision. Индекс: [[docs/architecture/akb/rfcs.yaml]].

### Знания (machine-readable)
- AKB: [[docs/architecture/akb/]] — laws.yaml, adrs.yaml, patterns/, standards/, tech_catalog.yaml, org_memory.yaml, evidence_levels.yaml, glossary.yaml, rfcs.yaml, history.yaml. Читается Hermes + tests/ (arch-gate), НЕ импортируется runtime (LAW K8).

## КОНСТИТУЦИЯ / МЕТОДОЛОГИЯ / НАУКА
- [[ADR-001 Kernel]] — Event Bus, Service Registry, Lifecycle
- [[ADR-002 Contracts]] — порты, Contract/Golden/Compat
- [[ADR-003 Event Bus]]
- [[ADR-004 Service Registry]]
- [[ADR-005 Resource Model]]

## Platforms (волны 3–14)
### Закрыты ✅
- [[ADR-006 Model Platform]] (Wave 3) — ILlm, OmniRoute/Ollama, ModelRegistry
- [[ADR-009 Policy Platform]] (Wave 5/5.1/5.2) — PolicyEngine + Budget/Privacy/Security/ProviderSelection
  - Legacy: [[ADR-007 Policy Platform — Design]] (superseded by ADR-009)
- [[ADR-010 Evaluation Platform]] (Wave 7) — MetricsCollector, BenchmarkRunner, Golden Dataset
- [[ADR-011 Knowledge Platform]] (Wave 8) — IEntityExtractor/IValidator/IFactChecker/IKnowledgeGraph
  - Legacy: [[ADR-008 Knowledge Platform]] (draft, superseded by ADR-011)
- [[ADR-012 Memory Platform]] (Wave 9) — IMemoryStore/ISemanticMemory/IProceduralMemory
- [[ADR-013 Workflow Platform]] (Wave 10) — IPlanner/IExecutor/IReflection/IRetryManager
- [[ADR-014 Agent Platform]] (Wave 11) — IAgentPlatform + AgentResult (оркестрация подсистем)
- [[ADR-015 Learning Platform]] (Wave 12) — ILearningStore/IPatternExtractor + ExecutionTrace
- [[ADR-016 Optimization Platform]] (Wave 13) — IOptimizer/IGuardrail + ConfigApplier (propose/approve/apply/rollback)
- [[ADR-017 Autonomous Hermes]] (Wave 14) — IAutonomyController/ISelfEvaluator/IDocMaintainer + LlmOptimizer (IOptimizer adapter)
- [[ADR-018 Bootstrap & Runtime Lifecycle]] (Bootstrap Initiative, Phase A — Composition Root; `in_progress`)
- [[ADR-019 Kernel Runtime Architecture]] (Bootstrap Initiative, Этап 1 — контракт ядра; Phase B–H следуют)
- [[Kernel Review (Phase 0.5)]] (финальная арх-ревизия: Inventory/DepAudit/Classification/Etc.)
- [[Bootstrap Initiative v2 — Master Roadmap]] (программа развития ядра: фазы A–L, DoD/Guardrails/Smoke)
- [[KROFT_OS Master Roadmap v2 —  một2 Levels + 3 Architecture Epics]] (дорожная карта ядра: Levels 1–12 + Runtime Resource Mgmt / IPC / Capability-Permission)
- [[KROFT_OS Master Development Plan v1.0]] (10 фаз развития ядра: программа v2.0 с DoD/Guardrails/Smoke)
- [[ADR-020 — Runtime Host Architecture]] (Architecture Freeze: вариант б утверждён; Kernel минимален, ComponentRegistry вместо Wrapper)
- [[ADR-021 Runtime Evolution — Architecture Intelligence Synthesis]] (research: OTP/K8s/Temporal/Dapr/Akka/Orleans/NATS/FDB/OTel/seL4 → supervision trees, declarative recovery, durable bus, virtual actors, chaos harness; LAW K1–K8 verified)
- [[ADR-022 Architecture Knowledge Base]] (machine-readable governance: laws.yaml + adrs.yaml + patterns + tech_catalog + history; enabler for Уровни 2/5 Review/Audit; AKB data in docs/architecture/akb/)
- [[ADR-023 Architecture Agent Hierarchy & Research Mesh]] (10-level maturity ladder + Research Mesh; KROFT-native agents via IAgentPlatform+Supervisor+EventBus; reuse existing substrate; LAW K1–K8 verified)
- [[ADR-024 Meta Architecture Engine (L11-L18) & EIP]] (L11 Meta→L18 Autonomous CTO + Engineering Intelligence Platform 4 contours; EIP = meta-layer OVER KROFT, NOT runtime (LAW K8); ADR-E Org Memory; heuristic>ML; human-in-loop self-improve)
- [[KROFT_OS Master Development Plan v3.0]] (переписан под компонентную модель: Runtime Host → Component Registry → Plugin Runtime; каждая фаза с DoD/Guardrails/Smoke)
- [[KROFT_OS Master Development Plan v2.0]] (12 фаз развития ядра: Phase 1 ✅, Phase 2 ✅, далее Runtime Services → Supervisor → Observability → Distributed → Security)
- [[Build Journal — Runtime Phase 1]] (Foundation: IKernel порт, runtime/* зависит только от contracts, python -m runtime -> Kernel READY)
- [[Build Journal — Runtime Phase 2]] (Platform Integration Core: manifest-based ComponentRegistry, 12 компонентов через IProcess, платформы не модифицированы)
- [[Build Journal — Runtime Phase 3]] (Observability Foundation: runtime/services/ Metrics/Config/Logging/Snapshot, висят на IEventBus, платформы нетронуты)
- [[Build Journal — Runtime Phase 4]] (Autonomous Recovery: ProcessState FSM, policy-driven Backoff, IComponentController, Panic L1/L2/L3, Recovery Journal)
- [[Build Journal — Runtime Phase 5]] (Hot Reload: ConfigService os.stat watch, ComponentController.swap, manifest reload, FileWatcher stdlib-only)
- [[Build Journal — Runtime Phase 6]] (Legacy Cleanup Track L: обнулены 6 pre-existing failures, regression 0 failures / 0 errors, runtime/services нетронуты)

### Не начаты ⬜
_(все 14 волн Roadmap закрыты)_

## Routing / Infrastructure (cross-cutting)
- [[ADR-007 Policy Platform — Superseded by ADR-009]] — история решения политики

## Specifications
- [[Kernel]] (spec)
- [[ResourceManager]] (spec)
- [[Scheduler]] (spec)

## Reviews & Decisions
- [[Architecture Review v1.0]] — CRITICAL: декомпозиция AgentService (R1), плагины-интенты

## Roadmap & Changelog
- [[ROADMAP.md]] — 14 волн, статусы
- [[RELEASES.md]] — changelog по волнам
- [[Build Journal — Wave 3-14]] — хронология коммитов + lessons learned + Bootstrap Initiative

## Templates (стили и шаблоны документов)
- [[madison_console_template]] — нео-бруталист hard-shadow «console» HTML-шаблон (Anton/Manrope/JetBrains Mono), используется для standalone-дашбордов/агентских UI
- [[MADISON//AI — Autonomous Ad Agency]] — пример приложения на шаблоне (single-file vanilla JS, 5 департаментов)

## Technical Debt (зафиксировано)
- `adapters/router.py` импортирует `services` — нарушение LAW 2 (baseline арх-гейта, pre-existing)
- `services/workflow_runner.py` cross-import sibling services (composition root Wave 10, гейт не знает)
- `services/agent_service.py` — 1106-строк regex-монолит (Open/Closed нарушен, см. Architecture Review R1)
- `services/session_store.py` — legacy parallel path к IMemoryStore (миграция v0.5)
- Папка репо `KnowledgeOS-v5` не переименована в `KROFT_OS` (OS-lock)

## Навигация по категориям (KMP §9)
Vision · Architecture · ADR · Specification · Platform · Kernel · Interface · Review · Decision · Technical Debt · Future Work
