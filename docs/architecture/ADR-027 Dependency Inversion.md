---
tags: [kroft, adr, adr-027, dependency-inversion, architecture, phase-b]
created: 2026-08-01
author: Hermes (Architecture Intelligence Protocol)
status: accepted
evidence_level: III
relates_to: [ADR-026, ADR-002, LAW-K1, LAW-K6, Dependency-Report-Phase-B]
laws_affected: [K1, K6]
summary: >
  Применение Dependency Inversion Principle ко всем слоям KROFT_OS: высокоуровневые
  модули (kernel, runtime, services) зависят от абстракций (contracts), а не от
  конкретных реализаций infrastructure/adapters. Устранение прямых cross-импортов
  (adapters→policies, services→concrete ModelRegistry).
---

# ADR-027 — Dependency Inversion

## 1. Context

LAW K1/K6 требуют, чтобы межслойное общение шло только через `contracts/`.
Dependency Report (Phase B) нашёл отклонения:

- **V2:** `kernel→infrastructure.SnapshotStore` (persistence-реализация в ядре).
- **V3:** `adapters/router.py:15 → from policies.budget_policy import estimate_cost`
  (adapters импортирует sibling-пакет policies напрямую).
- **V4:** `services/policy_engine.py:18 → from contracts.model_registry import ModelRegistry`
  (сервис зависит от КОНКРЕТНОГО класса в contracts, а не от порта).

## 2. Decision

1. Kernel и runtime зависят от `ISnapshotRepository` (порт), а не от
   `SnapshotStore` (реализация). Реализация инжектируется через Composition Root.
2. `adapters/router.py` НЕ импортирует `policies.*`. Вместо
   `estimate_cost` из `policies.budget_policy` — либо порт `IPolicy.estimate_cost`,
   либо передача callable через `contracts` (напр. `RouterPolicyHook`).
3. `ModelRegistry` в `contracts` переименовать/обернуть в порт `IModelRegistry`;
   `policy_engine` зависит от `IModelRegistry`, не от конкретного класса.

## 3. Consequences

- Все cross-layer вызовы типизированы портами → смена реализации не ломает вызывающий слой.
- Arch-gate расширяется (будущая версия) для ловли V3/V4 аналогов.
- V3 требует отдельного коммита (не в рамках kernel-decoupling V1/V2).

## 4. Evidence

- `patterns/forbidden.yaml` F2/F3 (runtime/kernel imports services; hardcoded dep in kernel).
- Dependency Report Phase B, V2/V3/V4.

---

## Approval (K5)

**Status: accepted** as of 2026-08-02 (TZ-003 WP-08, human-approved scope).
Implemented and verified in Phase B (ADR-026/027/028) and Phase C (ADR-029).
Evidence Level: III (implemented + architecture-gate green + 768 tests passing).
