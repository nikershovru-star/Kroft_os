---
id: ADR-035
title: "Tenant Isolation Architecture"
status: accepted
evidence_level: III
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
related: [TZ-MULTI-001, RFC-007, ADR-032, ADR-033, ADR-034]
law: [K1, K3, K5, K6, K8]
authors: [kroft-architect]
---

# ADR-035: Tenant Isolation Architecture

## Status

**Proposed** — ожидает K5-approval (подтверждение пользователем). Design-фаза
TZ-MULTI-001. Код (WP-01..WP-09) НЕ стартует без approval.

## Context

TZ-SEC-001 (ADR-032/033/034) дал capability-границу в едином пространстве. Для
multi-tenant сценариев требуется изоляция по оси «владелец пространства» (tenant).
Без неё нельзя безопасно запускать несколько независимых агентских сред в одном runtime.

## Decision

Ввести модель tenant как **explicit context**, передаваемый через порты:

1. **Ports** (`contracts/tenant/`, stdlib-only):
   - `TenantId` — value object, regex `[a-z0-9_-]{1,32}`
   - `ITenantContext` — `tenant_id`, `agent_id`, `metadata: Dict[str, str]`
   - `ITenantManager` — `create/get/exists/list/delete/set_metadata`
   - `ITenantIsolator` — `check_boundary`, `namespace_path`, `scope_key`
2. **Kernel logic** (`kernel/tenant/`, K1-clean — только contracts):
   - `TenantContext` (dataclass, реализует `ITenantContext`)
   - `TenantContextProvider` — thread-local + async-safe current-tenant storage
     (`set_current` / `get_current` / `clear`); fallback `DefaultTenantContext` (`"default"`)
3. **Services** (`services/tenant/`, contracts-only):
   - `InMemoryTenantManager` (default), `JsonlTenantManager` (optional persistence),
     `TenantRecord` (soft-delete + audit)
   - `create`/`delete` → `ApprovalManager.request()` (K5)

### Integration points (не дублируют TZ-SEC-001)
- `CapabilityManager`/`AuthorizationEngine`: `ctx` получает `tenant_id`; cross-tenant → `deny`
- `FileSandbox.set_tenant(t)`: добавляет `workspace/{t}/` к roots; `namespace_path` резолвит
- `SecretManager.get_for(t, key)`: lookup `{t}_{key}` (Q2 — расширение, не дубликат)
- `AuditLogger`: `record.tenant_id` добавляется автоматически
- `ApprovalManager`: reused для tenant create/delete

## Consequences

**Positive:**
- Двухосная изоляция (capability × tenant) без нарушения K1/K3.
- Обратная совместимость: 794 теста не ломаются (default tenant).
- Fail-closed: агент без tenant не стартует.

**Negative / Trade-offs:**
- Дополнительный context-propagation (через `TenantContextProvider`, не глобально).
- Memory/Graph isolation — через scope_key снаружи (Memory Platform не меняется, но
  вызывающий код должен применять namespace).

## Compliance
- **K1:** `kernel/tenant/` импортирует только `contracts/tenant/`, `contracts/security/`,
  stdlib. Проверяется arch-gate.
- **K3:** `TenantManager`/`TenantContextProvider` создаются только в `composition/`.
- **K5:** create/delete tenant → ApprovalManager (human-in-loop).
- **K6:** cross-tenant только через `ITenantIsolator.check_boundary()`.
- **K8:** tenant-метаданные — в `services/tenant/` persistence или AKB, не в `runtime/` ядре.

## Alternatives (см. RFC-007 §3)
A. os.environ/global — отвергнуто (K1/K8).
B. поле в RuntimeContext — отвергнуто (Q4, риск регрессии).
C. отдельный TenantSecretManager — отвергнуто (Q2, дубликат).
D. внешняя БД — отвергнуто (Q1, in-memory + optional JSONL).

## Open Questions (defaults, требуют подтверждения)
- Q1 persistence: in-memory default + optional JSONL.
- Q2 secrets: расширить `SecretManager.get_for`.
- Q3 admin: global admin видит все tenant через `list()`, но `set_current` требуется.
- Q4 RuntimeContext: обёртка `TenantContextProvider`, не меняем `runtime/`.
