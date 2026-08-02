---
title: "KROFT_OS — Project Status"
version: "1.0"
date: "2026-08-02"
status: "active"
lang: ru
purpose: >
  Краткий статус архитектурного долга и готовности подсистем.
  Дополняет PROJECT_CONTEXT_MAP.md (паспорт) и ARCHITECTURE_MAP.md (handoff).
  Single source для "где мы находимся" по архитектурным нарушениям.
---

# KROFT_OS — Project Status

## 0. TL;DR

**Архитектурный долг уровня HIGH: ЗАКРЫТ.** Все основные слои (kernel, runtime, services, adapters, infrastructure, policies) зависят ТОЛЬКО от `contracts`. Последнее известное нарушение (V3: adapters→policies) устранено в Phase C / WP-01.

**Статус платформы:** архитектурно стабильна (Clean/Hexagonal соблюдён), готова к функциональному развитию (Supervisor & Recovery, Distributed Runtime, Marketplace).

**Git-режим:** единый репозиторий (Variant A). Remote `origin` = github.com/nikershovru-star/Kroft_os (K5 push разрешён пользователем 2026-08-02).

---

## 1. Архитектурный долг (Architectural Debt)

### История нарушений

| ID | Нарушение | Слой → Слой | Закон | Статус | Закрыто |
|----|-----------|-------------|-------|--------|---------|
| **V1** | kernel импортирует `infrastructure.DependencyContainer` | kernel → infrastructure | K1 | ✅ CLOSED | Phase B.4 (commit 1bd9140) |
| **V2** | kernel импортирует `infrastructure.SnapshotStore` | kernel → infrastructure | K1 | ✅ CLOSED | Phase B.3 (IStateRepository port) |
| **V3** | `adapters/router.py` импортирует `policies.budget_policy.estimate_cost` | adapters → policies | K6 | ✅ CLOSED | Phase C.1 (commit 3a899c6, ADR-030) |
| **V4** | `services/policy_engine.py` импортирует `contracts.model_registry.ModelRegistry` | services → contracts (порт) | K6 (minor) | ⚠ ACCEPTED | model_registry — это порт, не нарушение K6 в строгом смысле |
| **Deprecated** | `Kernel(container=...)` legacy-параметр | kernel | K1/K3 (щель) | ✅ WP-07 (container-path оставлен как K3-compliant Composition Root factory, статус deprecated снят) | TZ-003 WP-07 |

### Текущий статус долга

- **HIGH architectural debt:** **0** (нет).
- **LOW/accepted debt:** 1 (V4, не критично, model_registry — порт).
- **Deprecated API:** **0** (legacy `Kernel(container=...)` de-deprecated in WP-07; container path is now the canonical Composition Root factory, K3-compliant).
- **Open violations:** **0** (arch-gate 14 passed).

> **No High Architectural Debt** — все критические нарушения закрыты.

---

## 2. Готовность подсистем

| Подсистема | Статус | Примечание |
|------------|--------|-----------|
| Kernel (lifecycle FSM) | ✅ done | UNINITIALIZED→INITIALIZED→RUNNING→STOPPED |
| Runtime (context, registry) | ✅ done | CapabilityRegistry, RuntimeContext |
| Contracts (27 портов) | ✅ done | чистые Protocol-интерфейсы |
| Services (Agent/Knowledge/...) | ✅ done (32) | зависят только от contracts |
| Adapters | ✅ done | НЕТ импорта policies (V3 closed) |
| Infrastructure | ✅ done | DependencyContainer, SnapshotStore, ... |
| Policies | ✅ done | PolicyRegistry + PolicyEngine (Phase C.2) |
| Composition Root | ✅ done | `composition/` (7 модулей, build_system) |
| Architecture Gate | ✅ done (WP-02) | 8 positive + 6 negative |
| CLI | ✅ done | main.py + commands + repl |
| Plugins | ⏸ empty | зарезервировано |

---

## 3. Метрики (реальный прогон 2026-08-02)

- **Tests:** `1002 passed, 19 skipped, 1 xpassed, 0 failed` (реальный прогон 2026-08-02; +ТЗ-CAUSAL-01: +9 тестов Lamport; WP14-RACE xfail'd)
- **Arch-gate:** `14 passed` (8 positive + 6 negative)
- **ADR:** 55 (ADR-001..055; ADR-055 accepted + Lamport amendment; ADR-007 — двойной файл, логически один)
- **Laws:** 8 (K1–K8)
- **Forbidden patterns:** 6 (F1–F6)
- **Open violations:** **0**
- **AKB YAML:** 16 файлов (laws, adrs, rfcs, history, issues, patterns/*, standards/*, glossary, evidence_levels, org_memory, tech_catalog, pattern_library, import_matrix, gate_coverage)

---

## 4. Следующие этапы (roadmap)

| Волна | WP (TZ-001/TZ-002) | Статус |
|-------|---------------------|--------|
| Wave 0 | WP-01 (V3), WP-02 (gate), WP-03 (docs) | ✅ WP-01, ✅ WP-02, ✅ WP-03 |
| Wave 1 | WP-04 (repo), WP-05 (CI), WP-06 (sync), WP-07 (deprecated), WP-08 (ADR lifecycle) | ✅ WP-04, ✅ WP-05, ✅ WP-06, ✅ WP-07, ✅ WP-08 |
| Wave 2 | WP-09 (KG v2 ✅ TZ-KNOW-001), WP-10 (Supervisor/Recovery ⏸ design RFC-010/ADR-038), WP-11 (self-analysis ✅ TZ-AGENT-001) | WP-10 design DONE, code ждёт K5 |
| TZ-EXECUTION-001 | WP-01 (Sandbox port+adapter), WP-02 (ToolRegistry+DesktopAdapter integration), WP-03 (tests +12) | ✅ DONE |
| Wave 3 | WP-12/13/14 DONE | ✅ COMPLETE |
| TZ-015 | Distributed Runtime Implementation (9 comps) | 🔧 CODE STARTED — ports+services scaffolded (gate C causal), in-process federation DONE; real network (TcpEventBus/partition) deferred (WP14-RACE infra) |
| TZ-016 | Autonomous Planner (8 comps) | 🔬 design RFC-016/ADR-045 DONE, code deferred |
| TZ-017 | Long-Term Memory Evolution (7 comps) | 🔬 design RFC-017/ADR-046 DONE, code deferred |
| TZ-018 | World Model (7 comps) | 🔬 design RFC-018/ADR-047 DONE, code deferred |
| TZ-019 | Agent Society (8 comps) | 🔬 design RFC-019/ADR-048 DONE, code deferred |
| TZ-020 | Self Improvement (8 comps) | 🔬 design RFC-020/ADR-049 DONE, code deferred |
| TZ-021 | AI Marketplace (8 comps) | 🔬 design RFC-021/ADR-050 DONE, code deferred |
| TZ-022 | Federated Knowledge Network (8 comps) | 🔬 design RFC-022/ADR-051 DONE, code deferred |
| TZ-023 | Cognitive Operating System (8 comps) | 🔬 design RFC-023/ADR-052 DONE, code deferred |
| **v2.0 Roadmap** | TZ-015..023 unified (ADR-053) | 🔬 ALL DESIGNS DONE (9×8/8 PASS, gate 14, akb-lint PASSED) |
| **ADR-054** | Cognitive Kernel Constitution (CONSTITUTION, 20 invariants I-01..I-20) | ✅ ACCEPTED — primary invariant, all TZ subordinate |
| **ADR-055** | ConfidenceScore Contract (unified cross-entity) | ✅ ACCEPTED (derived from I-12; aggregation rule added) |
| Compatibility Matrix | ADR-044..053 vs ADR-054 | ✅ DONE — 9/10 compatible, 4 critical clarifications |

### 4.1 Нумерационный reconciliation (Флаг 4, 2026-08-02)

**Source of Truth выбран явно: KROFT_OS ADR-053 + PROJECT_STATUS (v2.0 roadmap).** Любая
внешняя/устаревшая карта (напр. v1-таблица из стартового промпта, где `TZ-015 = Reasoning
Engine (W2)`) — НЕ SoT, должна считаться archived и заменена на ADR-053.

**Mapping (внутренний ADR/RFC-трекер ↔ карта W-волн):**
| Внутренний номер | Что реализует | На карте W-волн (ADR-053) |
|------------------|---------------|---------------------------|
| TZ-015 / ADR-044 / RFC-015 | Distributed Runtime (CRDT/Elector/Bus + Shared Context + causal-merge) | **W3**: Shared Context (TZ-023) + Federation Layer (TZ-024) + Network Layer (TZ-028) |
| Reasoning Engine (компонент) | WorldModel-backed reasoning в фазе Deliberate | **W2**: Deliberate = Reasoning (WorldModel ADR-047 / TZ-018) → Planning (TZ-016) → Decision (I-03) |

**Открытый пробел W2 (честно):** dedicated **Reasoning Engine как отдельный КОМПОНЕНТ**
(Planner/Solver/Inference Engine) НЕ выделен — в FSM покрыт фазой `Deliberate`
(Reasoning→Planning→Decision в общем виде), но параметризуемого движка (Intent/Attention/
WorldState-управляемого) как самостоятельного модуля нет. → W2 статус (~60%) СКОРРЕКТИРОВАН
вниз: фаза есть, компонента-движка нет. Это НЕ блокирует code-фазу, но должно быть в трекере
как явный gap, а не «планируется» без уточнения.


**Integration slice (path 3, 2026-08-02):** ядро × федерация связаны in-process (2 kernel + 2 SharedContextService, in-memory канал). Доказано: federated-факт (CausalMark A,lamport=10) достигает узла B и МЕНЯЕТ Decision@B через WorldState — KROFT_OS когнитивная ОС, не distributed store с LLM. CausalMark.__lt__ исправлен на lamport-primary (был node-name-primary — неверный merge); далее ТЗ-CAUSAL-01 повысил CausalMark до Lamport clock с receive-обновлением (закрыт дефект «talkative node wins»).

**ТЗ-CAUSAL-01 (2026-08-02, DONE — code):** CausalMark → Lamport logical clock. `merge_remote` и `InMemoryWorldState.update` делают `receive` при получении удалённого факта (clock = max+1); локальные события (tick/emit) делают `tick()`; stored marks сохраняют remote origin для конвергентности; idempotent replay. Commits 65a3ee2 (contract) + 3724248 (tests). Ad-hoc 13/13 PASS; 19 causal-тестов PASS; full 1002/0; gate 14/14; issues `CAUSAL-SEQ-LIMIT` CLOSED. ADR-055 amended (§6 Lamport contract, status accepted).

**Следствие для статус-дашборда:** W3 (Shared Context + causal-merge) РЕАЛЬНО частично сделан
(in-process) — карта/PROJECT_STATUS это отражают (TZ-015 = CODE STARTED, не deferred).
Реальная сеть (TcpEventBus/partition/reconnect) и dedicated Reasoning Engine остаются OPEN.

### Функциональные этапы (после стабилизации)
- Phase D — Configuration & Secrets
- Phase E — MCP Gateway
- Phase F — Supervisor & Recovery
- Phase G — Distributed Runtime

---


## 5. Stage Audit (2026-08-02)

- **Stage 22** — НЕ пропущен. Упоминается в CHANGELOG («без --auth сервер ведёт себя как Stage 22»); это был HTTP server / auth stage, влился в последующие.
- **Stage 47 / 48** — ДЕЙСТВИТЕЛЬНО ОТСУТСТВУЮТ в CHANGELOG (Stage 46 v5.9.0 → Stage 49 v5.12.0; версии v5.10.0/v5.11.0 пропущены) и в README. **Решение: intentionally skipped (не технический долг).**
  - *Audit evidence (2026-08-02):* Graph visualization — Stage 23 дал export DOT/JSON/GEXF, НЕТ interactive renderer; real-time collaboration — НЕ реализовано; plugin marketplace — Stage 25/40 дали loader, НЕТ marketplace/dep-management; LLM-based agent — НЕ реализовано (Hermes v2 = Wave 3).
  - *Гипотезы содержимого:* Stage 47 ≈ Graph Visualization / Interactive Renderer (gap после analytics Stage 46); Stage 48 ≈ Real-time Collaboration / Multi-user ИЛИ Plugin Marketplace.
  - *Почему skipped:* не блокируют core functionality; покрываются roadmap Wave 3 (ADR-025 multimodal, Distributed Runtime Phase G); могут быть отдельными ТЗ позже.
  - *Статус:* documented as skipped placeholder (graph-viz + real-time-collab / plugin-marketplace).
- **ADR-025** (PHASE 6 Multimodal) — status `proposed`, K5 decision **defer to Wave 3** (no IMultimodalParser port; heavy deps need optional adapters per K8; not blocking).

> **v1.0 changelog:** создан в рамках TZ-002 (D2). Зафиксирован V1/V2/V3 CLOSED, No High Architectural Debt, метрики 768 passed / 0 failed / 0 open violations.