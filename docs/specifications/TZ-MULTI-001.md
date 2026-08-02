---
id: TZ-MULTI-001
title: "Multi-User Isolation & Tenant Model"
priority: Critical
status: Incoming
dependencies:
  - TZ-SEC-001 (Secure Runtime & Capability System) — DONE
  - ADR-032 (Security Architecture) — accepted
  - ADR-033 (Capability Model) — accepted
  - ADR-034 (Approval Workflow) — accepted
  - RFC-006 (Secure Runtime) — under_review
date: "2026-08-02"
---

# TZ-MULTI-001: Multi-User Isolation & Tenant Model

## 1. Executive Summary

TZ-MULTI-001 вводит **модель арендатора (tenant)** в KROFT_OS. Каждый агент, пользователь или сессия работает внутри строго изолированного контекста `tenant_id`. Изоляция распространяется на runtime, storage, memory, knowledge graph и capability-boundary.

**Зачем:** TZ-SEC-001 построил capability-границу (RBAC + approval), но предполагал единое глобальное пространство. Для multi-user / multi-team / multi-agent сценариев нужна **вторая ось изоляции** — tenant. Capability отвечает на вопрос «что можно делать?», tenant — на вопрос «в чьём пространстве?».

**Критичность:** High. Без tenant-изоляции нельзя безопасно запускать несколько независимых агентских сред в одном runtime.

---

## 2. Baseline Re-Verify (фактура на момент старта)

После TZ-SEC-001 (commits eacd554 → 4215de4) в системе:

| Компонент | Статус | Где |
|-----------|--------|-----|
| CapabilityManager (RBAC) | DONE | `kernel/security/capability_manager.py` |
| AuthorizationEngine | DONE | `kernel/security/policy_engine.py` |
| ApprovalManager | DONE | `kernel/security/approval_manager.py` |
| FileSandbox | DONE | `kernel/security/sandbox.py` |
| SecretManager | DONE | `services/security/secret_manager.py` |
| AuditLogger (checksum-chain) | DONE | `services/security/audit_logger.py` |
| TerminalExecutor | DONE | `services/security/terminal_executor.py` |
| Security ports (8 шт.) | DONE | `contracts/security/__init__.py` |
| Tool.required_capabilities | DONE | `contracts/agent.py` |
| Arch-gate | 14 passed | `tests/test_architecture*.py` |
| Full suite | 794 passed | `tests/` (вкл. 26 security tests) |

**Важно:** `kernel/` содержит `kernel.py`, `__init__.py` и подпакет `security/`. Подпакета `tenant/` нет. `RuntimeContext` (в `runtime/`) не содержит поля `tenant_id`. `FileSandbox` не знает о tenant-prefix. `Memory Platform` / `Knowledge Graph` — shared (нет namespace-изоляции).

---

## 3. Requirements

### 3.1 Functional (R)

| ID | Requirement | Priority | Law |
|----|-------------|----------|-----|
| **R1** | **Tenant Identity.** Каждый агент при старте получает `tenant_id: str`. Без tenant_id агент не стартует (fail-closed). | Must | K1 |
| **R2** | **Runtime Context Isolation.** `tenant_id` передаётся через `RuntimeContext` (или аналогичный порт), но **не через глобальную переменную** и не через `os.environ`. | Must | K1, K8 |
| **R3** | **Storage Namespace.** Файловые операции агента ограничены префиксом `workspace/{tenant_id}/`. FileSandbox из TZ-SEC-001 расширяется tenant-scoped roots. | Must | K6 |
| **R4** | **Memory & Knowledge Isolation.** Graph-узлы, RAG-индекс и memory-записи автоматически префиксируются `tenant:{tenant_id}:`. Cross-tenant read → `deny`. | Must | K6 |
| **R5** | **Capability Scoping.** Роли (Role) по умолчанию глобальны, но tenant-админ может назначать **tenant-specific overrides** (добавить/забрать capability в рамках одного tenant). | Should | K5 |
| **R6** | **Cross-Tenant Boundary.** Агент из `tenant=A` **не может** вызывать, читать, писать или видеть ресурсы `tenant=B`. Проверка на границе — в `AuthorizationEngine` (расширение TZ-SEC-001 WP-03). | Must | K6 |
| **R7** | **Tenant Admin & Onboarding.** Создание/удаление tenant требует human approval (K5) через `ApprovalManager`. Soft-delete + полный audit trail. | Must | K5, K4 |
| **R8** | **Agent Affinity.** Агент привязан к tenant при инстанцировании. Runtime-миграция между tenant запрещена. | Must | K2 |
| **R9** | **Default Tenant.** Для обратной совместимости существующих тестов и агентов предусмотрен tenant `"default"`. Он не даёт дополнительных прав, только namespace. | Must | — |
| **R10** | **Tenant-scoped Secrets.** `SecretManager` расширяется: ключ `OPENAI_API_KEY` в tenant `"acme"` читается как `acme_OPENAI_API_KEY` (или через `ITenantSecretManager` порт). | Should | — |

### 3.2 Non-Functional (N)

| ID | Requirement |
|----|-------------|
| **N1** | **K1-Compliance.** `kernel/tenant/` импортирует **только** `contracts/tenant/`, `contracts/security/`, `runtime/`, stdlib. Никаких `services/`, `adapters/`, `infrastructure/`. |
| **N2** | **K3-Compliance.** `TenantManager` и `TenantContextProvider` создаются и связываются **только** в `composition/`. |
| **N3** | **Performance.** Lookup `tenant_id` → O(1). Не блокирует event loop / thread pool. |
| **N4** | **Backward Compatibility.** Все существующие тесты (794 шт.) продолжают проходить без изменений (tenant `"default"`). |
| **N5** | **Test Coverage.** `tests/tenant/` ≥ 95% покрытие, включая negative tests (cross-tenant penetration). |
| **N6** | **AKB Sync.** Каждый WP порождает evidence; ADR-035 регистрируется в `adrs.yaml` с `evidence_level: III`. |

---

## 4. Architecture Constraints (LAW)

| Закон | Применение |
|-------|------------|
| **K1** | `kernel/tenant/` — только contracts + stdlib. `kernel/security/` уже K1-clean; `kernel/tenant/` повторяет паттерн. |
| **K3** | `TenantManager(...)` вызывается только из `composition/build_system.py` или аналога. |
| **K5** | `TenantManager.create_tenant()` + `delete_tenant()` → `ApprovalManager.request()` → human `decide()`. Без approval — `deny`. |
| **K6** | Cross-tenant вызовы невозможны напрямую. Только через `ITenantIsolator.check_boundary()` (explicit port). |
| **K8** | Tenant-метаданные (список tenant, политики) — в `docs/` (AKB) или `services/tenant/` persistence. Не в `runtime/` ядре. |

---

## 5. Work Packages (WP)

### WP-01: Tenant Context Ports (`contracts/tenant/`)
**Scope:** Определить порты, через которые весь остальной код общается с tenant-моделью.

**Артефакты:**
- `contracts/tenant/__init__.py`
- `TenantId` — value object (str, regex `[a-z0-9_-]{1,32}`)
- `ITenantContext` — порт: `tenant_id`, `agent_id`, `metadata: Dict[str, str]`
- `ITenantManager` — порт: `create()`, `get()`, `exists()`, `list()`, `delete()`, `set_metadata()`
- `ITenantIsolator` — порт: `check_boundary(src_tenant, dst_tenant)`, `namespace_path(tenant_id, path)`, `scope_key(tenant_id, key)`

**K1:** Этот модуль — stdlib only. Никаких импортов `services/`.

---

### WP-02: Runtime Tenant Context (`kernel/tenant/`)
**Scope:** Чистая (K1-clean) логика внедрения tenant в runtime.

**Артефакты:**
- `kernel/tenant/__init__.py`
- `TenantContext` — dataclass, реализация `ITenantContext`
- `TenantContextProvider` — thread-local + async-safe storage текущего tenant. Методы:
  - `set_current(ctx: ITenantContext)` — для composition/CLI
  - `get_current() -> ITenantContext` — для kernel/services
  - `clear()` — при завершении сессии
- `DefaultTenantContext` — fallback `tenant_id="default"`

**Критерий:** `kernel/tenant/` не импортирует `services/`. Проверяется arch-gate.

---

### WP-03: Tenant Manager (`services/tenant/`)
**Scope:** IO-реализация управления tenant. Тяжёлый слой — за границей kernel.

**Артефакты:**
- `services/tenant/__init__.py`
- `InMemoryTenantManager` — default, thread-safe `Dict[str, TenantRecord]`
- `JsonlTenantManager` — optional, append-only JSONL persistence (audit-friendly)
- `TenantRecord` — `tenant_id`, `created_at`, `created_by`, `metadata`, `deleted: bool`

**Интеграция:** При `create()` — автоматический вызов `ApprovalManager.request()` (K5). При `delete()` — soft delete + audit.

---

### WP-04: Storage Isolation (FileSandbox Extension)
**Scope:** Расширить `FileSandbox` из TZ-SEC-001 WP-06 для tenant-scoped paths.

**Артефакты:**
- `FileSandbox.set_tenant(tenant_id: str)` — добавляет `workspace/{tenant_id}/` к resolved roots
- `FileSandbox.namespace_path(tenant_id, relative_path)` → абсолютный путь внутри tenant-пространства
- Проверка: `is_allowed` отвергает пути, содержащие `../` или уходящие за пределы tenant-root

**К1:** Изменения в `kernel/security/sandbox.py` — только stdlib + contracts. Никаких `services/`.

---

### WP-05: Memory & Knowledge Isolation
**Scope:** Tenant-scoped namespace для Memory Platform и Knowledge Graph.

**Артефакты:**
- `TenantMemoryNamespace` — helper: `scope_key(tenant_id, key)` → `tenant:acme:memory:node_42`
- `TenantRAGFilter` — фильтр RAG-запросов по `tenant_id` (интеграционная точка с ADR-025 / PHASE 6)
- `TenantKnowledgeBoundary` — проверка при graph-traverse: узел принадлежит тому же tenant?

**Примечание:** Это НЕ требует переписывания `Memory Platform` (ADR-012). Namespace применяется **снаружи** через `ITenantIsolator.scope_key()` при записи/чтении.

---

### WP-06: Multi-Agent Tenant Coordination
**Scope:** Правила взаимодействия агентов внутри и между tenant.

**Артефакты:**
- `TenantCoordinationPolicy` — правило: агенты внутри одного tenant делят `CapabilityContext` (shared), но каждый имеет свой `agent_id`
- `AuthorizationEngine.authorize_cross_tenant()` — расширение WP-03 TZ-SEC-001. Всегда `deny` (R6).
- `AgentResult.tenant_id` — добавить поле в trace (K4)

---

### WP-07: Tenant Admin & Onboarding
**Scope:** UX создания tenant + назначение ролей.

**Артефакты:**
- `TenantOnboardingWorkflow` — последовательность:
  1. User запрашивает `create_tenant("acme")`
  2. `ApprovalManager` создаёт `ApprovalRequest` (K5)
  3. Human `decide(approve=True)`
  4. `TenantManager.create()` + `CapabilityManager.register_role_for_tenant()` (R5 override)
  5. `AuditLogger` фиксирует факт
- `DefaultTenantRoles` — при создании tenant назначаются роли: `Admin` (владелец), `Operator` (технический)

---

### WP-08: Tests (`tests/tenant/`)
**Scope:** Полное покрытие tenant-слоя.

**Тесты (целевой набор):**
- `test_tenant_context_provider_thread_safety` — параллельные потоки, разные tenant
- `test_default_tenant_fallback` — без explicit set → "default"
- `test_tenant_manager_create_requires_approval` — K5
- `test_tenant_manager_soft_delete` — delete → exists=False, audit есть
- `test_file_sandbox_tenant_prefix` — path внутри tenant-root разрешён, снаружи — deny
- `test_cross_tenant_memory_isolation` — scope_key разный для разных tenant
- `test_authorization_engine_denies_cross_tenant` — agent A (tenant=acme) → ресурс B (tenant=corp) = deny
- `test_secret_manager_tenant_prefix` — `acme_OPENAI_API_KEY` vs `corp_OPENAI_API_KEY`
- `test_backward_compat_794_regression` — полный suite не падает

**Цель:** ≥ 26 тестов, покрытие ≥ 95%.

---

### WP-09: Documentation & ADR
**Scope:** Фиксация знаний.

**Артефакты:**
- `ADR-035 Tenant Isolation Architecture.md` — proposed → accepted (после K5)
- `docs/specifications/TZ-MULTI-001.md` — этот документ (уже есть)
- `PROJECT_CONTEXT_MAP.md` v1.5 — обновить §6 (metrics: 820+ tests), §2 (добавить `kernel/tenant/`, `services/tenant/`), §4 (ADR-035)
- `AKB/history.yaml` — entry `WP-MULTI-001-design` / `WP-MULTI-001-code`

---

## 6. Integration with TZ-SEC-001

TZ-MULTI-001 **не дублирует** TZ-SEC-001, а **расширяет** его:

| TZ-SEC-001 | TZ-MULTI-001 (расширение) |
|------------|---------------------------|
| `CapabilityManager.authorize(ctx, cap)` | `ctx` теперь содержит `tenant_id`; проверка cross-tenant перед capability |
| `FileSandbox.is_allowed(path)` | `FileSandbox.is_allowed(tenant_id, path)` — tenant-prefix |
| `SecretManager.get(key)` | `TenantSecretManager.get(tenant_id, key)` — prefix lookup |
| `AuditLogger.log(record)` | `record.tenant_id` добавляется автоматически |
| `ApprovalManager` | Reused для tenant create/delete (K5) |

---

## 7. Acceptance Criteria (Definition of Done)

- [ ] `contracts/tenant/` содержит ≥ 3 порта (`ITenantContext`, `ITenantManager`, `ITenantIsolator`)
- [ ] `kernel/tenant/` K1-clean (arch-gate проходит: нет импорта `services/`, `adapters/`, `infrastructure/`)
- [ ] `services/tenant/` реализует `ITenantManager` (in-memory + optional JSONL)
- [ ] `FileSandbox` поддерживает tenant-prefix (WP-04)
- [ ] Cross-tenant доступ возвращает `AuthDecision.deny` (negative test доказывает)
- [ ] Default tenant `"default"` не ломает существующие 794 теста (regression gate)
- [ ] Новые tenant-тесты: ≥ 26, покрытие ≥ 95%
- [ ] Полный suite: ≥ 820 passed, 0 failed, arch-gate 14 passed
- [ ] `ADR-035` создан, зарегистрирован в AKB, `evidence_level: III`
- [ ] `PROJECT_CONTEXT_MAP.md` обновлён до v1.5
- [ ] `akb_lint.py` — PASSED

---

## 8. Open Questions (Defaults — подтверди или скорректируй)

| ID | Вопрос | Default |
|----|--------|---------|
| **Q1** | **Tenant persistence.** Только in-memory (при перезапуске — чисто) или обязательна JSONL persistence? | In-memory default + optional JSONL (`TenantManager(persistence_path=...)`). Без внешней БД. |
| **Q2** | **Tenant-scoped secrets.** SecretManager расширяется префиксом (`{tenant}_{key}`) или создаём отдельный `TenantSecretManager` порт? | Расширить существующий `SecretManager` методом `get_for(tenant_id, key)`. Не дублировать. |
| **Q3** | **Cross-tenant admin.** Роль `Admin` видит все tenant (global) или только свой? | Global admin видит все tenant через `TenantManager.list()`, но explicit `set_current(tenant_id)` требуется для операций. Default tenant — не даёт global прав. |
| **Q4** | **Tenant в RuntimeContext.** Добавляем поле `tenant_id` в существующий `RuntimeContext` (runtime/) или создаём обёртку `TenantRuntimeContext` в `kernel/tenant/`? | Обёртка `TenantRuntimeContext` в `kernel/tenant/` (K1-clean), не меняем `runtime/` напрямую. |

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **R1.** Изменение `RuntimeContext` сломает существующие тесты. | `TenantContextProvider` — обёртка, не модификация `RuntimeContext`. Default tenant `"default"` — прозрачный fallback. |
| **R2.** FileSandbox tenant-prefix сломает Windows-пути (пробелы, длина). | `pathlib.Path` + `os.path.normcase`. Graceful degradation: если путь > 240 символов — `deny` с reason. |
| **R3.** Memory isolation требует изменений в `Memory Platform` (ADR-012). | Namespace применяется через `ITenantIsolator.scope_key()` **перед** вызовом Memory Platform. Memory Platform не меняется. |
| **R4.** Scope creep — tenant начинает проникать в kernel, нарушая K1. | Arch-gate ловит автоматически. Код review: `kernel/tenant/` только contracts + stdlib. |

---

## 10. Related Documents

- **TZ-SEC-001** — foundation (capability, approval, audit)
- **ADR-032** — Security Architecture (accepted)
- **ADR-033** — Capability Model (accepted)
- **ADR-034** — Approval Workflow (accepted)
- **ADR-035** — *Tenant Isolation Architecture* (требуется, proposed)
- **RFC-006** — Secure Runtime (under_review, tenant — extension)
- **AKB/import_matrix.yaml** — требуется добавить `kernel/tenant/` → `contracts/tenant/` (K1)

---

## 11. Execution Protocol (LAW K5 + K8)

1. **Design-фаза** (этот документ → RFC-007 + ADR-035 draft → K5-approval → ADR accepted)
2. **Код-фаза** (WP-01..WP-08 атомарными коммитами, pytest между шагами)
3. **Верификация** (ad-hoc verify + full suite + arch-gate + akb-lint)
4. **Docs-фаза** (PROJECT_CONTEXT_MAP v1.5, history.yaml)

**Код НЕ стартует без твоего "go" (K5).** Жду approval на design или правки в Q1–Q4.
