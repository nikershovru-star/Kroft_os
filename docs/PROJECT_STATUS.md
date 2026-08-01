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

**Git-режим:** единый репозиторий (Variant A), финализирован в WP-04. `.gitignore` исключает `data/`, `*.exe`, `.hermes/`, `archive/KnowledgeOS-v5/`, `recovery_journal.jsonl`, `stubs/`, `.venv/`, `cache/`. Local git remote ОТСУТСТВУЕТ — `git push` запрещён (LAW K5).

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
- **Deprecated API:** **0** (container-path оставлен как K3-compliant Composition Root factory, deprecated-статус снят в WP-07 TZ-003).
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

- **Tests:** `768 passed, 19 skipped, 0 failed`
- **Arch-gate:** `8 passed` (positive) + `6 passed` (negative)
- **ADR:** 31 (ADR-001..031; ADR-007 — двойной файл, логически один)
- **Laws:** 8 (K1–K8)
- **Forbidden patterns:** 6 (F1–F6)
- **Open violations:** **0**
- **AKB YAML:** 15 файлов (laws, adrs, patterns/*, standards/*, glossary, rfcs, history, evidence_levels, org_memory, tech_catalog, pattern_library, import_matrix, gate_coverage)

---

## 4. Следующие этапы (roadmap)

| Волна | WP (TZ-001/TZ-002) | Статус |
|-------|---------------------|--------|
| Wave 0 | WP-01 (V3), WP-02 (gate), WP-03 (docs) | ✅ WP-01, ✅ WP-02, ✅ WP-03 |
| Wave 1 | WP-04 (repo), WP-05 (CI), WP-06 (sync), WP-07 (deprecated), WP-08 (ADR lifecycle) | ✅ WP-04, ✅ WP-05, ✅ WP-06, ✅ WP-07, ✅ WP-08 |
| Wave 2 | WP-09 (KG v2), WP-10 (Supervisor/Recovery), WP-11 (self-analysis) | ⏸ pending |
| Wave 3 | WP-12 (Arch Intelligence), WP-13 (Multimodal) | ⏸ pending |

### Функциональные этапы (после стабилизации)
- Phase D — Configuration & Secrets
- Phase E — MCP Gateway
- Phase F — Supervisor & Recovery
- Phase G — Distributed Runtime

---

> **v1.0 changelog:** создан в рамках TZ-002 (D2). Зафиксирован V1/V2/V3 CLOSED, No High Architectural Debt, метрики 768 passed / 0 failed / 0 open violations.
