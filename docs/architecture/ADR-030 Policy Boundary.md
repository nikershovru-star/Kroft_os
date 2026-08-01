---
tags: [kroft, adr, adr-030, policy-boundary, architecture, phase-c]
created: 2026-08-01
author: Hermes (Architecture Intelligence Protocol)
status: proposed
relates_to: [ADR-009, ADR-026, ADR-027, ADR-028, LAW-K6, Dependency-Report-Phase-B]
laws_affected: [K6]
summary: >
  Устранить последнее серьёзное нарушение слоёв (V3): adapters/router.py
  импортировал policies.budget_policy.estimate_cost напрямую. Введён порт
  estimate_cost на уровне contracts (contracts/cost.py), а PolicyRegistry делает
  политики подключаемыми по имени. PolicyEngine pipeline (veto→filter→rank→
  fallback) уже реализует C.3. После Phase C все основные слои зависят только
  от contracts.
---

# ADR-030 — Policy & Domain Boundary (Phase C)

## 1. Context

Phase B очистила kernel (K1 resolved). Последнее HIGH-нарушение — **V3**
(ADR-027, Dependency Report Phase B): `adapters/router.py:15` делал
`from policies.budget_policy import estimate_cost`. Это ломает правило
**Adapters → Contracts ← Policies** (LAW K6): адаптеры не должны знать о
конкретных политиках.

`estimate_cost` — чистая эвристика от `ModelQuery` + `ModelInfo` (оба — порты
в `contracts.i_llm`). Она НЕ семантика политики, поэтому должна жить на уровне
`contracts`, доступном и адаптерам, и политикам.

## 2. Decision

### C.1 — V3 resolution (Boundary port)
- Создан `contracts/cost.py::estimate_cost(query, model)` — чистая функция на
  портах `contracts.i_llm`. Единый источник истины.
- `adapters/router.py` импортирует `from contracts.cost import estimate_cost`
  (больше НЕ `from policies...`).
- `policies/budget_policy.py` использует `contracts.cost.estimate_cost`
  (убрано дублирование).
- Architecture Gate усилен: `policies` добавлен в `PROJECT_PKGS` + `ALLOWED`;
  `adapters` разрешено импортировать ТОЛЬКО `contracts`. Любой возврат
  `from policies` в adapters будет пойман тестом (negative-test verified).

### C.2 — PolicyRegistry (pluggability)
- `policies/registry.py::PolicyRegistry` — именованный реестр:
  `register("budget", BudgetPolicy())`, `get`, `has`, `names`, `all()`
  (sorted by priority). Политики становятся подключаемыми как плагины.
- `PolicyEngine.register_all(policies)` — bulk-регистрация из реестра.

### C.3 — Policy Pipeline (already implemented)
`PolicyEngine.decide()` реализует pipeline:
```
Request → Veto (can_veto, asc priority) → Catalog Filter → Ranking
        → Fallback chain → Execution+retry (FallbackPolicy)
```
Это основа Enterprise-режима. C.3 считается ВЫПОЛНЕННЫМ (был в Wave 5).

## 3. Consequences

**Positive:**
- V3 (последний HIGH долг) устранён; `adapters` зависит только от `contracts`.
- Все основные слои (kernel, runtime, services, adapters, infrastructure,
  policies) теперь зависят ТОЛЬКО от `contracts` — платформенная чистота.
- Политики подключаемы по имени (расширяемость без правки ядра).

**Negative / Risks:**
- `policies` теперь в `PROJECT_PKGS` arch-gate — если policies начнёт
  импортировать adapters/services, гейт упадёт (это правильно, защита K6).

## 4. Evidence

- `contracts/cost.py` — `estimate_cost` порт
- `adapters/router.py:13` — `from contracts.cost import estimate_cost`
- `policies/registry.py` — `PolicyRegistry`
- `services/policy_engine.py:50` — `register_all`
- `tests/test_architecture.py` — `policies` в `PROJECT_PKGS` + `ALLOWED`,
  negative-test подтвердил защиту V3
- Regression: 757 passed, 19 skipped, arch-gate 3 passed
