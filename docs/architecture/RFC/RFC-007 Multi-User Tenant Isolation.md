---
id: RFC-007
title: "Multi-User Tenant Isolation Model"
status: under_review
date: "2026-08-02"
related: [TZ-MULTI-001, ADR-035, RFC-006, ADR-032, ADR-033, ADR-034]
authors: [kroft-architect]
evidence_level: III
---

# RFC-007: Multi-User Tenant Isolation Model

## 1. Problem

TZ-SEC-001 (ADR-032/033/034) построил capability-границу (RBAC + approval) в едином
глобальном пространстве. Для multi-user / multi-team / multi-agent сценариев этого
недостаточно: агенты разных владельцев не должны видеть чужие файлы, memory, граф или
секреты. Нужна **вторая ось изоляции** — tenant (арендатор), отвечающая на вопрос
«в чьём пространстве выполняется операция?».

## 2. Proposal

Ввести `tenant_id` как first-class контекст, передаваемый явно через порты (не через
`os.environ`, не через глобальную переменную — K1/K8). Архитектурно повторяем паттерн
TZ-SEC-001: **ports в `contracts/tenant/`, чистая логика в `kernel/tenant/`
(K1-clean), тяжёлый IO в `services/tenant/`**.

### 2.1 Слои

| Слой | Назначение | K1 |
|------|-----------|-----|
| `contracts/tenant/` | Порты: `ITenantContext`, `ITenantManager`, `ITenantIsolator` + `TenantId` VO | stdlib |
| `kernel/tenant/` | `TenantContext` (dataclass), `TenantContextProvider` (thread/async-local), `DefaultTenantContext` | только contracts |
| `services/tenant/` | `InMemoryTenantManager` (default), `JsonlTenantManager` (optional persistence), `TenantRecord` | contracts-only (не kernel) |

### 2.2 Изоляция по осям

- **Runtime** (R2): `TenantContextProvider.get_current()` возвращает `ITenantContext`;
  `AuthorizationEngine` получает `tenant_id` из контекста. Fail-closed: без tenant — deny.
- **Storage** (R3): `FileSandbox.set_tenant(t)` добавляет `workspace/{t}/` к roots;
  `namespace_path(t, rel)` → абсолютный путь. `../` и выход за tenant-root → deny.
- **Memory/Graph** (R4): `ITenantIsolator.scope_key(t, key)` → `tenant:{t}:{key}`;
  применяется **снаружи** Memory Platform (ADR-012 не меняется).
- **Secrets** (R10, Q2): расширить `SecretManager.get_for(t, key)` → lookup `{t}_{key}`.
- **Cross-tenant** (R6): `AuthorizationEngine.authorize_cross_tenant()` всегда `deny`;
  проверка идёт через `ITenantIsolator.check_boundary()`.
- **Admin/Onboarding** (R7): `create_tenant`/`delete_tenant` → `ApprovalManager.request()`
  (K5); soft-delete + audit.

### 2.3 Default tenant (R9)

Для обратной совместимости `TenantContextProvider` без explicit set возвращает
`DefaultTenantContext` (`tenant_id="default"`). Существующие 794 теста не меняются.

## 3. Alternatives Considered

- **A. Глобальная переменная / os.environ.** Отвергнуто: нарушает K1/K8 (неявное
  состояние, не тестируемо, утечки между агентами в одном процессе).
- **B. Поле `tenant_id` прямо в `RuntimeContext` (runtime/).** Отвергнуто (Q4):
  меняет runtime-ядро, риск регрессии 794 тестов. Выбрана обёртка `TenantContextProvider`
  в `kernel/tenant/`.
- **C. Отдельный `TenantSecretManager` порт.** Отвергнуто (Q2): дублирует `SecretManager`;
  выбрано расширение методом `get_for`.
- **D. Внешняя БД для tenant.** Отвергнуто (Q1): in-memory default + optional JSONL,
  без внешней зависимости.

## 4. Risks

- **R1.** Регрессия тестов → митигируется обёрткой + default tenant.
- **R4.** Scope creep в kernel → arch-gate ловит (K1 детектор).

## 5. Decision Needed

K5-approval на ADR-035 (Tenant Isolation Architecture). После approval — код WP-01..WP-09.
