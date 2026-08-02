---
title: "KROFT_OS — Project Context Map"
version: "1.2"
date: "2026-08-02"
status: "active"
lang: ru
purpose: >
  Компактный архитектурный паспорт для AI-моделей и инженеров.
  Читается ПЕРЕД любой работой с кодом или документами.
  Содержит: слои, правила, статус, структуру, запреты.
  v1.2: синхронизация с реальностью после Phase B/C + WP-01/WP-02
  (Variant A DONE, Composition Root = composition/, V3 CLOSED, ADR-030,
  arch-gate 8 positive + 6 negative, import_matrix.yaml + gate_coverage.md).
---

# KROFT_OS — Project Context Map v1.2

## 0. Что такое KROFT_OS

**KROFT_OS** (Knowledge Runtime & Orchestration Framework Technology Operating System) — инженерная операционная система для создания, управления и эволюции AI-агентов.

Это НЕ приложение и НЕ набор скриптов. Это **саморазвивающаяся инженерная платформа**, где знания, архитектура, код, решения и эксперименты связаны в единую систему.

Цель: среда, в которой AI-агенты исследуют, создают, хранят знания, проверяют архитектуру, выполняют задачи, анализируют ошибки и улучшают систему через контролируемую эволюцию.

---

## 1. Архитектурные слои (сверху вниз)

```
KP (Philosophy)
    ↓ рождает
LAW (Policy: K1-K8 + F1-F6 forbidden patterns)
    ↓ констреинит
KRM (Reference Model) — метамодель сущностей
    ↓ определяет сущности для
KERA (Engineering Reference Architecture) — конституция системы
    ↓ описывает слои
    CORE (kernel / runtime / contracts)
    SERVICE (Agent / Knowledge / Memory / Workflow / Evaluation / Security / Model Platforms)
    META (Research Mesh / AKB / Architecture Intelligence / Evolution Engine)
    ↓ методология изменений
KEH (Engineering Handbook)
    ↓ наука доказательств
KES (Engineering Science)
    ↓ универсальный словарь
KL (Language)
    ↓ предложения до принятия
RFC (Request for Comments)
    ↓ принятые решения
ADR (Architecture Decision Records) + AKB (Architecture Knowledge Base)
    ↓ исполняется в
Runtime / Applications
```

| Слой | Расшифровка | Файлы | Назначение |
|------|-------------|-------|------------|
| **KP** | Philosophy | `docs/architecture/KP/` | 7 принципов (Knowledge > Code, Evidence > Opinion, Architecture > Features, Small Kernel, Composable Systems, Humans Approve, Everything Measurable) |
| **KRM** | Reference Model | `docs/architecture/KRM/` | Метамодель: 16 entity-types (Knowledge, Artifact, Decision, Capability, Contract, Platform, Agent, Component, Signal, Boundary, State, Projection, Policy, Resource, Workflow, Evidence) |
| **KERA** | Engineering Reference Architecture | `docs/architecture/KERA/` | Конституция: 3 уровня (Core / Service / Meta), 6 Views (Logical, Runtime, Deployment, Knowledge, Security, Evolution) |
| **KEH** | Engineering Handbook | `docs/architecture/KEH/` | Как правильно менять систему: Research, ADR, Benchmark, Documentation, Review, Experiment Handbooks |
| **KES** | Engineering Science | `docs/architecture/KES/` | Как доказать правильность: Research Science, Decision Science, Benchmark Science, Reliability Science, Economics, Human Factors |
| **KL** | Language | `docs/architecture/KL/` | Убиквитарный язык: термины, определения, запрещённые синонимы |
| **RFC** | Request for Comments | `docs/architecture/RFC/` | Предложения до ADR. Статусы: draft → under_review → decided / rejected / superseded |
| **AKB** | Architecture Knowledge Base | `docs/architecture/AKB/` | Машиночитаемая память: YAML (laws, adrs, patterns, standards, glossary, rfcs, history, evidence_levels, org_memory, tech_catalog, pattern_library) |
| **ADR** | Architecture Decision Records | `docs/architecture/ADR-*.md` | Принятые решения. ADR-001..034. Плоское хранение (не в подпапке), имена с пробелами |

---

## 2. Структура репозитория (Variant A — ВЫПОЛНЕН)

```
KROFT_OS/                    ← единый git-репозиторий (Variant A DONE)
├── docs/
│   ├── architecture/
│   │   ├── KP/  KRM/  KERA/  KEH/  KES/  KL/  RFC/  AKB/   ← 8 подпапок (см. §1)
│   │   ├── ADR-001.md .. ADR-034.md                     ← плоские файлы (имена с пробелами)
│   │   ├── ARCHITECTURE_MAP.md                          ← handoff-карта
│   │   └── PROJECT_CONTEXT_MAP.md                       ← этот паспорт
│   ├── PROJECT_STATUS.md                                ← статус арх-долга (см. D2)
│   └── README-overview.md
├── kernel/  contracts/  runtime/  services/  adapters/
├── kernel/security/   ← capability boundary core (TZ-SEC-001, K1-clean: contracts-only)
├── kernel/tenant/     ← tenant context carrier (TZ-MULTI-001, K1-clean: contracts-only)
├── services/security/  ← secret/audit/terminal IO (TZ-SEC-001, contracts-only)
├── services/tenant/    ← tenant manager/isolator/onboarding IO (TZ-MULTI-001, contracts-only)
├── services/knowledge_graph/  ← graph engine, AKB sync, auto-linker (TZ-KNOW-001, K8 meta-layer)
├── services/agent_orchestration/  ← orchestrator, messenger, healing, recorder (TZ-AGENT-001)
├── services/self_analysis/  ← self-analysis engine (TZ-AGENT-001, K8 meta-layer)
├── composition/   ← Composition Root (слой сборки, K3)
├── cli/  infrastructure/  plugins/  policies/  tests/  main.py  bootstrap_v2.py
```

**Variant A vs Г (решено):** единый репозиторий создан (2026-08-01). Код KnowledgeOS-v5 перенесён в `KROFT_OS/`; история сохранена. `docs/` — В GIT (часть единого repo). Local git remote ОТСУТСТВУЕТ — коммиты только локальные, `git push` запрещён (LAW K5).

**Слои (физические каталоги):**
- `kernel/` — микроядро (lifecycle FSM, Kernel). Импортирует ТОЛЬКО `contracts`, `runtime`, stdlib (K1).
- `runtime/` — RuntimeContext, CapabilityRegistry, Supervisor, Recovery. Импортирует `contracts`, stdlib (K1, K8).
- `contracts/` — порты (27 Protocol-интерфейсов). stdlib only.
- `services/` — прикладной слой (Agent, Knowledge, Memory, Workflow, Evaluation, ...). `contracts` + stdlib ONLY.
- `adapters/` — конкретные реализации портов (LocalFileSystemAdapter, ...). `contracts` + stdlib ONLY (K6 — НЕТ импорта `policies`).
- `infrastructure/` — реализации портов (InMemoryEventBus, InMemoryGraphBuilder, SnapshotStore, DependencyContainer, ConfigLoader). `contracts` + stdlib.
- `policies/` — политики (BudgetPolicy, PolicyRegistry, PolicyEngine). `contracts` + stdlib ONLY.
- `composition/` — **Composition Root** (единственный слой сборки, K3). `build_system()` собирает все объекты. Импортирует ВСЁ.
- `cli/` — entrypoint (main.py, commands, repl). `composition` + `contracts`.
- `plugins/` — пуст (зарезервирован). `contracts` + stdlib.
- `bootstrap_v2.py` — **thin entrypoint**: делегирует в `composition.build_system()` (НЕ Composition Root сам по себе).

---

## 3. Архитектурные законы (LAW K1–K8 + F1–F6)

Источник: `docs/architecture/AKB/laws.yaml` + `AKB/patterns/forbidden.yaml`.
Читаются Architecture Gate (`tests/test_architecture.py` + `tests/test_architecture_negative.py`). Нарушение K-закона = block.

| ID | Закон | Суть | Severity |
|----|-------|------|----------|
| **K1** | `kernel-imports-only-contracts` | Ядро импортирует ТОЛЬКО `contracts/` + `runtime/`. Никогда `services/`, `adapters/`, `infrastructure/`, `policies/` | block |
| **K2** | `services-dont-modify-kernel` | Сервисы НЕ модифицируют ядро. Расширение только через порты | block |
| **K3** | `wiring-only-in-composition` | Создание/связывание объектов — ТОЛЬКО в `composition/`. Ядро не инстанцирует DependencyContainer/SnapshotStore | block |
| **K4** | `artifacts-traceable` | Каждый вывод агента — frozen + traceable (who, when, why) | warn |
| **K5** | `human-approve-required` | Критические изменения требуют подтверждения человека (deploy, ADR, self-improve) | block |
| **K6** | `explicit-boundaries` | Межслойное общение ТОЛЬКО через `contracts/` или EventBus. Никаких прямых вызовов через границу (adapters → policies ЗАПРЕЩЕНО) | block |
| **K7** | `atomic-commits` | Коммиты атомарны по фазе; `git add -A` запрещён; только поименованные файлы | warn |
| **K8** | `architecture-intelligence-outside-runtime` | Интеллект (AKB, Research Mesh, LLM) живёт в `docs/` + `services/`, НИКОГДА в `runtime/` или `kernel/` | block |

**Forbidden Patterns (F1–F6)** — автоматически ловятся arch-гейтом (AUTOMATED/PARTIAL см. §Architecture Gate):

| ID | Паттерн | Суть | Статус |
|----|---------|------|--------|
| **F1** | `blocking-sleep-in-recovery` | Блокирующий sleep в recovery/supervisor | AUTOMATED (WP-02) |
| **F2** | `runtime-imports-services` | runtime/ импортирует services/ (нарушение K1/K3) | AUTOMATED (через K1) |
| **F3** | `hardcoded-dependency-in-kernel` | хардкод зависимости в kernel/ | AUTOMATED (K1 + K3) |
| **F4** | `meta-layer-in-runtime` | мета-слой (AKB/LLM) в runtime/ (нарушение K8) | AUTOMATED (WP-02) |
| **F5** | `untraceable-agent-result` | AgentResult без trace (нарушение K4) | PARTIAL (if present) |
| **F6** | `adr-without-evidence` | ADR без уровня доказательства (KES#1) | PARTIAL (warn, WP-08) |

---

## 4. Ключевые ADR (ADR-001..034, без пропусков)

Источник: `docs/architecture/ADR-*.md` + `AKB/adrs.yaml`. Полный индекс ниже (D9).

| ADR | Тема | Статус | Законы |
|-----|------|--------|--------|
| ADR-001 | Kernel | accepted | K1, K3 |
| ADR-002 | Contracts | accepted | K1 |
| ADR-003 | Event Bus | accepted | K1, K6 |
| ADR-007 | Policy Platform (superseded by ADR-009; см. примечание) | superseded | K3 |
| ADR-009 | Policy Platform (итоговый) | accepted | K3, K5 |
| ADR-010 | Evaluation Platform | accepted | K4 |
| ADR-011 | Knowledge Platform | accepted | K1, K2 |
| ADR-012 | Memory Platform | accepted | K1, K2 |
| ADR-013 | Workflow Platform | accepted | K3, K4 |
| ADR-014 | Agent Platform | accepted | K4, K5, K8 |
| ADR-018 | Bootstrap & Runtime Lifecycle | accepted | K1, K3 |
| ADR-019 | Kernel Runtime Architecture | accepted | K1, K3 |
| ADR-020 | Runtime Host Architecture | accepted | K1, K3, K8 |
| ADR-021 | Architecture Intelligence Synthesis | accepted | K1, K8 |
| ADR-022 | AKB (machine-readable governance) | accepted | K8 |
| ADR-023 | Agent Hierarchy & Research Mesh | accepted | K1, K3, K4, K5, K8 |
| ADR-024 | Meta Engine & EIP | accepted | K3, K8 |
| ADR-025 | Multimodal Knowledge Engine (PHASE 6) | proposed | K8, K4, K3 |
| ADR-026 | Plugin Registry & Marketplace | accepted | III | TZ-001 WP-09 |
| ADR-027 | Dependency Injection via Constructor | accepted | III | TZ-001 WP-10 |
| ADR-028 | Kernel Purity (no infra imports) | accepted | III | TZ-001 WP-11 |
| ADR-029 | Composition Root Pattern | accepted | III | TZ-001 WP-12 |
| ADR-030 | Policy Boundary (Phase C) | proposed | K6 |
| ADR-031 | CI Pipeline & AKB Linter | proposed | K5, K7, K8 |
| ADR-032 | Security Architecture (Capability Boundary) | proposed | K1, K3, K5, K8 |
| ADR-033 | Capability Model (RBAC + Tool Requirements) | proposed | K1, K5, K6 |
| ADR-034 | Approval Workflow (Human-in-loop) | accepted | K5 |
| ADR-035 | Tenant Isolation Architecture | accepted | K1, K3, K5, K6, K8 | TZ-MULTI-001 |
| ADR-036 | Knowledge Graph v2 Architecture | accepted | K8 |
| ADR-037 | Agent Orchestration & Self-Analysis | accepted | K8 |

> Примечание: ADR-007 существует в двух редакциях (`ADR-007 Policy Platform — Design (superseded draft).md` и `ADR-007 Policy Platform — Superseded by ADR-009.md`). Обе помечены superseded; итоговый — ADR-009. ADR-008 (Knowledge Platform) переименован в ADR-011 (см. AKB/adrs.yaml). Индекс ADR-001..034 — **без пропусков** (ADR-007 двойной, ADR-008 → ADR-011).

### Полный индекс ADR (D9)

```
ADR-001 Kernel
ADR-002 Contracts
ADR-003 Event Bus
ADR-004 Service Registry
ADR-005 Resource Model
ADR-006 Model Platform
ADR-007 Policy Platform (superseded draft)  [+ ADR-007 superseded by ADR-009]
ADR-008 → ADR-011 Knowledge Platform
ADR-009 Policy Platform
ADR-010 Evaluation Platform
ADR-011 Knowledge Platform
ADR-012 Memory Platform
ADR-013 Workflow Platform
ADR-014 Agent Platform
ADR-015 Learning Platform
ADR-016 Optimization Platform
ADR-017 Autonomous Hermes
ADR-018 Bootstrap & Runtime Lifecycle
ADR-019 Kernel Runtime Architecture
ADR-020 Runtime Host Architecture
ADR-021 Runtime Evolution — Architecture Intelligence Synthesis
ADR-022 Architecture Knowledge Base
ADR-023 Architecture Agent Hierarchy & Research Mesh
ADR-024 Meta Architecture Engine (L11-L18) & EIP
ADR-025 Multimodal Knowledge Engine
ADR-026 Composition Root
ADR-027 Dependency Inversion
ADR-028 Kernel Purity
ADR-029 Bootstrap Lifecycle
ADR-030 Policy Boundary
ADR-031 CI Pipeline & AKB Linter
ADR-032 Security Architecture (Capability Boundary)
ADR-033 Capability Model (RBAC + Tool Requirements)
ADR-034 Approval Workflow (Human-in-loop)
```

> Примечание: ADR-007 существует в двух редакциях (`ADR-007 Policy Platform — Design (superseded draft).md` и `ADR-007 Policy Platform — Superseded by ADR-009.md`). Обе помечены superseded; итоговый — ADR-009. ADR-008 (Knowledge Platform) переименован в ADR-011 (см. AKB/adrs.yaml). Индекс ADR-001..034 — **без пропусков** (ADR-007 двойной, ADR-008 → ADR-011).

## 5. Убиквитарный язык (KL) — ключевые термины

Источник: `docs/architecture/AKB/glossary.yaml`.

| Термин | Определение | Запрещённые синонимы |
|--------|-------------|---------------------|
| **Agent** | Автономный компонент, реализующий `IAgentPlatform`; выполняет goal → AgentResult | Worker, Executor, Assistant, Bot |
| **Platform** | Крупная подсистема экосистемы (Research/Runtime/Knowledge/...) | Subsystem, Service-layer |
| **Kernel** | Минимальное ядро (`kernel/`), импортирует только `contracts` + `runtime` | Core, Engine |
| **Capability** | Атомарная функция, предоставляемая компонентом через порт | Feature, Function |
| **Research** | Сбор и синтез инженерных знаний (Research Mesh) | Investigation, Study |
| **Evidence** | Доказательство с Evidence Level (I–V, KES#1) | Proof, Source |
| **Artifact** | Persist-вывод агента/процесса | Output, Result |
| **Knowledge** | Накопленные инженерные знания (AKB + Knowledge Platform) | Data, Info |
| **Loop** | Замкнутый feedback-контур EIP | Cycle, Pipeline |
| **Composition Root** | Точка сборки компонентов (`composition/`, `build_system()`) | Wiring, Bootstrap, `bootstrap_v2` (это thin entrypoint, НЕ CR) |
| **Experiment** | Контролируемое изменение (Hypothesis → Metrics → Result) | Test, Trial |

**Правило:** один термин = одно понятие. Синонимы запрещены. `bootstrap_v2` — НЕ Composition Root (это thin entrypoint; реальный CR = `composition/`).

---

## 6. Текущий статус (audit 2026-08-02)

### ✅ Готово
- [x] KP Philosophy (7 принципов)
- [x] KL Language + Glossary (glossary.yaml)
- [x] RFC Layer (rfcs.yaml)
- [x] KERA Views (6 представлений)
- [x] KEH / KES restructuring (MOC-навигация)
- [x] AKB model (13 YAML + patterns/standards)
- [x] KRM v1.0 (16 entity-types)
- [x] Docs reorg в подпапки (KP/KRM/KERA/KEH/KES/KL/RFC/AKB)
- [x] **Variant A — единый git-репозиторий** (docs + code + история)
- [x] **Phase B** — kernel decoupled from infrastructure (K1 clean)
- [x] **Phase C / WP-01** — V3 (adapters→policies) CLOSED (ADR-030)
- [x] **WP-02** — Architecture Gate расширен: 8 positive + 6 negative тестов
- [x] **Architecture Gate — РАБОТАЕТ** (ловит K1/K3/K6/K8 + F1/F4 автоматически)

### 🔢 Метрики (реальный прогон 2026-08-02)
- **Tests:** `883 passed, 19 skipped, 0 failed` (вкл. `tests/security/` 26, `tests/tenant/` 28, `tests/knowledge_graph/` 32, `tests/agent_orchestration/` 31)
- **Arch-gate:** `14 passed` (8 positive + 6 negative, proof-of-fire)
- **ADR:** 36 (ADR-001..036), из них ADR-025 — proposed (PHASE 6), ADR-026..029 — **accepted** (WP-08 TZ-003), ADR-030 — proposed, ADR-031 — proposed (CI, WP-05), ADR-032/033/034 — **accepted** (Security, TZ-SEC-001), ADR-035 — **accepted** (Tenant, TZ-MULTI-001), ADR-036 — **accepted** (Knowledge Graph, TZ-KNOW-001); ADR-007 — двойной файл (superseded, логически один)
- **RFC:** 9 (RFC-001..004 + RFC-006/007/008/009 under_review; примечание: «RFC-005» НЕ существует — CI Pipeline это ADR-031, не RFC)
- **Security layer:** `kernel/security/` (capability/approval/sandbox, K1-clean) + `services/security/` (secret/audit/terminal, contracts-only)
- **Tenant layer:** `kernel/tenant/` (context provider, K1-clean) + `services/tenant/` (manager/isolator/onboarding, contracts-only)
- **Import matrix:** `AKB/import_matrix.yaml` (single source)
- **Gate coverage:** `AKB/gate_coverage.md`
- **Открытые нарушения:** **0** (V1/V2 закрыты в Phase B; V3 закрыт в Phase C)

### 🔜 Впереди
- [x] **TZ-003 Wave 1** — WP-04..WP-08 (repo/CI/sync/deprecated/ADR-lifecycle) DONE
- [x] CI/CD pipeline (WP-05 TZ-003) — DONE
- [x] **TZ-SEC-001** (Secure Runtime & Capability System) — DONE (ADR-032/033/034 accepted; WP-01..WP-09 + 26 tests)
- [x] **TZ-MULTI-001** (Multi-User Isolation & Tenant Model) — DONE (ADR-035 accepted; WP-01..WP-09: ports, context provider, manager/isolator, sandbox-tenant, memory-isolation, cross-tenant authz, onboarding, 28 tests; WP-10 docs)
- [x] **TZ-KNOW-001** (Knowledge Graph v2) — DONE (ADR-036 accepted; WP-01..WP-09: graph engine, AKB sync, auto-linker, evidence, query, MOC, 32 tests; docs)
- [x] **TZ-AGENT-001** (Multi-Agent Orchestration & Self-Analysis) — DONE (ADR-037 accepted; WP-01..WP-09: FSM, orchestrator, messenger, self-analysis, healing, graph integration, 31 tests)
- [ ] Knowledge Graph v2 (связи между ADR/Component/Experiment)
- [ ] Architecture Intelligence (Hermes v2.0) — частично (ADR-021/023/024)
- [ ] Runtime self-analysis
- [ ] **ADR-025 → accepted** (PHASE 6 Multimodal: код MK-001..005 ещё не написан)

---

<!-- AUTO-GENERATED-START -->
## 6.1 Auto-Generated Metrics (CI, do not edit by hand)

> Этот блок генерируется `tools/context_map_sync.py` из фактических прогонов.
> Ручное изменение чисел здесь → CI падает (drift detection).

- **Tests:** 854 passed (run `python scripts/ci.py`)
- **Arch-gate:** 14 passed (8 positive + 6 negative)
- **ADR:** 36 (ADR-001..036)
- **Open violations:** 0
<!-- AUTO-GENERATED-END -->

---

## 7. Architecture Gate (D6, WP-02)

Источник: `tests/test_architecture.py` + `tests/test_architecture_negative.py`.
Матрица импортов: `AKB/import_matrix.yaml` (single source of truth).

### Positive tests (8, blocking)
| Тест | Проверяет |
|------|-----------|
| `test_no_forbidden_cross_layer_imports` | K1/K6 import-axis (все слои) |
| `test_each_layer_respects_its_axis` | ALLOWED == матрица из YAML |
| `test_services_do_not_cross_import` | F2/F3 (services не импортят services) |
| `test_wiring_only_in_composition` | K3 (kernel/runtime/services/policies не инстанцируют DependencyContainer/SnapshotStore) |
| `test_kernel_runtime_no_ai_imports` | K8/F4 (kernel/runtime → akb/research/llm запрещены) |
| `test_no_blocking_sleep_in_recovery` | F1 (нет blocking sleep в recovery/supervisor) |
| `test_agent_result_frozen` | F5 (AgentResult frozen dataclass, если есть) |
| `test_all_adrs_have_evidence` | F6 (ADR evidence_level report, non-blocking warn) |

### Negative tests (6, proof-of-fire)
| Тест | Доказывает |
|------|-----------|
| `test_negative_k1_kernel_imports_infra` | K1 детектор ловит kernel→infrastructure |
| `test_negative_k6_adapters_imports_policies` | K6 детектор ловит adapters→policies (V3 regression guard) |
| `test_negative_k3_kernel_instantiates_container` | K3 детектор ловит kernel инстанцирует DependencyContainer |
| `test_negative_k8_kernel_imports_ai` | K8 детектор ловит kernel→akb/research/llm |
| `test_negative_f1_recovery_blocking_sleep` | F1 детектор ловит blocking time.sleep |
| `test_positive_gate_still_passes_on_real_code` | sanity: реальный код проходит |

Фикстуры: `tests/fixtures_violations/violation_*.py`.

### Coverage report (D7)
`AKB/gate_coverage.md` — явная матрица: какие законы AUTOMATED (K1/K3/K6/K8 + F1/F4), какие PARTIAL/warn (F5/F6), какие НЕ автоматизированы (K2/K4/K5/K7 — процесс/семантика).

---

## 8. AKB Structure (D7)

Источник истины для архитектурных правил: `docs/architecture/AKB/`.

| Файл | Назначение |
|------|-----------|
| `laws.yaml` | LAW K1–K8 |
| `adrs.yaml` | ADR-001..034 (decision, status, evidence_level) |
| `patterns/forbidden.yaml` | F1–F6 (enforcement статусы) |
| `patterns/allowed.yaml` | разрешённые паттерны |
| `import_matrix.yaml` | **матрица разрешённых импортов (WP-02, single source для гейта)** |
| `gate_coverage.md` | **отчёт покрытия гейта (WP-02)** |
| `standards/coding.yaml` | стандарты кода |
| `standards/interfaces.yaml` | стандарты интерфейсов |
| `glossary.yaml` | KL термины |
| `rfcs.yaml` | RFC-001..004 + RFC-006 |
| `evidence_levels.yaml` | уровни доказательств I–V |
| `tech_catalog.yaml` | каталог технологий |
| `history.yaml` | история изменений (включая WP-02, TZ-002) |
| `org_memory.yaml` | организационная память (ADR-E) |
| `pattern_library.yaml` | библиотека паттернов PL1–PL10 |

---

## 9. Правила для AI-моделей (обязательны к исполнению)

### ДЕЛАТЬ
1. **Анализируй** существующую архитектуру ПЕРЕД написанием кода.
2. **Проверяй** KP / KERA / KL перед любыми изменениями.
3. **Ищи** существующие решения в AKB (`laws.yaml`, `adrs.yaml`, `pattern_library.yaml`).
4. **Предлагай** RFC перед большими изменениями.
5. **Создавай** ADR после принятия решения (с Evidence Level, KES#1).
6. **Храни** знания после изменений (update AKB, history, org_memory).
7. **Прогоняй arch-gate** (`pytest tests/test_architecture.py tests/test_architecture_negative.py`) перед коммитом волны.

### НЕ ДЕЛАТЬ
1. **НЕ** пиши код без проверки архитектуры.
2. **НЕ** создавай новые термины без обновления KL (glossary.yaml).
3. **НЕ** создавай ADR без RFC для больших изменений.
4. **НЕ** добавляй сервисы в `kernel/` (LAW K1/K3).
5. **НЕ** смешивай `docs/` и `runtime/` (LAW K8).
6. **НЕ** используй `git add -A` (LAW K7).
7. **НЕ** нарушай границы слоёв (LAW K6).
8. **НЕ** делай `git push` — remote отсутствует, коммиты локальны.
9. **НЕ** используй `bootstrap_v2` как Composition Root — реальный CR = `composition/`.

---

## 10. Как читать этот файл (MOC)

- **Новая модель / инженер:** раздел 0 → 3 (LAW) → 9 (правила).
- **Архитектор:** 1 (слои) → 2 (структура) → 4 (ADR) → 6 (статус).
- **Разработчик:** 5 (KL) → 3 (LAW) → 9 (DO/DON'T).
- **Исследователь:** 1 → KES/KEH → AKB/org_memory.yaml.

---

## 11. Связанные файлы (must-read при глубокой работе)

| Задача | Файлы |
|--------|-------|
| Понять философию | `KP/KROFT Philosophy (KP).md` |
| Понять метамодель | `KRM/KROFT Reference Model (KRM) v1.0.md` |
| Понять архитектуру | `KERA/KROFT Engineering Reference Architecture (KERA) v1.0.md` + `KERA Views/*.md` |
| Проверить термин | `AKB/glossary.yaml` + `KL/KROFT Language (KL).md` |
| Проверить закон | `AKB/laws.yaml` + `AKB/patterns/forbidden.yaml` |
| Проверить решение | `ADR-*.md` + `AKB/adrs.yaml` + `AKB/org_memory.yaml` |
| Проверить импорт-матрицу | `AKB/import_matrix.yaml` |
| Проверить покрытие гейта | `AKB/gate_coverage.md` |
| Предложить изменение | `RFC/KROFT RFC Layer.md` + `KEH/KROFT Engineering Handbook (KEH).md` |
| Доказать решение | `KES/KROFT Engineering Science (KES).md` + `AKB/evidence_levels.yaml` |
| Найти шаблон | `AKB/pattern_library.yaml` + `AKB/patterns/allowed.yaml` |
| Проверить историю | `AKB/history.yaml` |

---

> **Запомни:** KROFT_OS строит не только код. Она строит организационную память. Код можно переписать. Потерянное знание «почему сделали так» — нет.
>
> **v1.7 changelog:** TZ-AGENT-001 Code DONE (WP-01..WP-09). Agent orchestration + runtime self-analysis: `contracts/agent_orchestration/` (ports + VO), `kernel/agent_lifecycle/` (FSM K1-clean), `services/agent_orchestration/` (orchestrator, messenger EventBus, healing, recorder), `services/self_analysis/` (health, drift). 31 agent tests. Suite 883 passed, gate 14, K8 verified. ADR-037 accepted.