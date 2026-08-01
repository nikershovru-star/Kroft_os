---
tags:
  - kroft
  - architecture
  - policy
  - wave5
  - adr
created: 2026-07-31
status: archived
superseded_by: "ADR-009 Policy Platform"
version: 1.0
updated: 2026-07-31
author: Chief Knowledge Architect (Hermes)
summary: >-
  Ранний ADR-007 политики, архивирован — полностью заменён ADR-009 (Wave 5/5.1/5.2).
  Историческая справка, не актуально.
---

# ADR-007 — Policy Platform

> Кандидат ADR-007 (нумерация унифицирована: см. [[ROADMAP]] / `docs/architecture/`).
> Связано: [[ADR-002 Contracts]], [[ADR-005 Resource Model]], [[ADR-006 Model Platform]].

> **Contract stub only.** Порт `IPolicy` создан в `contracts/i_policy.py` без
> реализации (Wave 1: Contracts Before Code). Архитектурные решения НЕ приняты —
> ждём дизайн-черновик пользователя. Связано с [[Master Architecture Roadmap]],
> [[Model Platform — Architecture (ADR-033)]] и [[Policy Engine — Design (Wave 5)]].

## Статус

- [x] Порт `IPolicy` (интерфейс): `select()` / `on_failure()` / `check()`
- [x] `PolicyContext` (user/session/tenant/offline/cost/latency/residency)
- [x] `PolicyDecision` (allow/model/reason/degraded/warnings)
- [ ] Реализация — **блокируется дизайном** (см. открытые вопросы)
- [ ] Тесты — после реализации

## Правило Wave 5 (из roadmap)

> Ни один запрос не выполняется без проверки Policy Engine.
> Любое нарушение политики блокируется автоматически.

Категории проверок (roadmap Wave 5): Privacy, Security, Budget, Offline Mode,
Tenant Rules, Data Residency, Secret Management.

## Открытые архитектурные вопросы (принять в сессии Wave 5)

1. **Где хранить бюджет?** stateless vs sqlite vs graph-node (влияет на state).
2. **Fallback** — внутри Policy (`on_failure`) или обёртка вокруг `ILlm`?
3. **Очередь (async) или синхронный greedy?** (queue нужна при конфликте квот)
4. **Policy = пассивный фильтр или активный актор?** (зависит ли от Registry)

## Связи с Model Platform (ADR-033)

- Policy оборачивает `ModelRegistry.select()` (Wave 4) + `ILlm.complete()` (Wave 3).
- `LlmResponse` уже несёт observability (`actual_model`, `cost`, `latency_ms`) —
  Policy может читать их для budget/post-hoc контроля.
- SSE (Wave 7.5) — отложен, не влияет на Policy интерфейс.

## Guardrail против «вечной архитектуры»

Как только дизайн придёт — реализация одним коммитом (контракт уже есть),
без переписывания порта. Регистрация в `contracts/__init__.py` после утверждения.
