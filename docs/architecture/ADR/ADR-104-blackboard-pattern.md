# ADR-104 — Blackboard Pattern (координационное состояние задачи)

- **Status:** proposed
- **Date:** 2026-08-07
- **Addresses:** отсутствовал профильный документ про фундаментальный паттерн обмена контекстом между агентами KROFT_OS. Поиск по «blackboard pattern» возвращал шум из чужих заметок (см. Search Quality v0.1, 2026-08-07) — дефицит контента, не баг поиска.
- **Supersedes / Relates:** ADR-103 (Agent Runtime), ADR-013 (Workflow Platform), RFC-009 (Multi-Agent Orchestration), RFC-010 (Supervisor & Recovery), ADR-034 (Approval Workflow), ADR-030 (Policy Boundary).
- **Implementation refs:** `contracts/i_blackboard.py` (`IBlackboard`, `BlackboardEntry`, `BlackboardContention`), `services/blackboard.py` (`InMemoryBlackboard`), `services/agent_runtime.py` (`delegate_step` пишет в `team.{goal_id}` scope), `services/coordination_strategy.py` (`StigmergyStrategy`).

---

## 1. Context & Problem

Агенты KROFT_OS (Research / Architect / Programmer / Writer / Planner / Finance) **не вызывают друг друга напрямую** — это жёсткое ограничение (ADR-103 §1, K1/K6: контекст только через blackboard / `IEventBus`). Нужен механизм обмена промежуточными результатами, статусами и handoff-сигналами между шагами одной задачи и между агентами, который:

- не создаёт прямых зависимостей агент→агент (decoupling);
- детерминирован и воспроизводим (I-09);
- устойчив к конкурентной записи без блокировок (lost updates недопустимы);
- читается как immutable snapshot (audit-friendly).

Без такого механизма мультиагентная координация вырождается либо в god-object оркестратора, либо в race-condition при shared state.

---

## 2. Decision

Использовать **Blackboard Pattern** как единственный канал обмена контекстом между агентами внутри задачи.

Контракт (`IBlackboard`):

- **Versioned, append-only.** Каждая запись несёт монотонный `version` + `seq` внутри scope → детерминизм и audit-trail.
- **Single-writer-per-scope.** Scope блокируется за `writer_id` при первой `append`. Попытка записать тот же scope **другим** writer-ом → `BlackboardContention` (raise, без блокировок). Это устраняет lost updates без мьютексов.
- **Snapshot-read.** `snapshot(scope)` возвращает read-only снимок всех entries на текущую version. Один writer не меняется при чтении.
- **Scopes изолируют контекст.** Конвенция: `team.{goal_id}` — общий контекст задачи; `team.{goal_id}.{step}` — промежуточный результат шага.

Реализация: `InMemoryBlackboard` (Phase C, Wave C1) — in-memory, append-only, single-writer.

---

## 3. Application in KROFT_OS

Поток обмена (из `AgentRuntime.delegate_step` + `StigmergyStrategy`):

1. `delegate_step(parent_goal_id, child_goal)` исполняет агента через `MultiAgentExecutor`.
2. Результат шага агент (или runtime) пишет в blackboard: `blackboard.append(scope=f"team.{goal_id}", writer_id=executor_id, payload=outcome.detail)`.
3. Следующий шаг **читает snapshot** этого scope (stigmergy: агенты «читают следы» предыдущих, не вызывая их) и дописывает под своим `writer_id`.
4. Human Approval Gate (ADR-034) консультируется для sensitive capabilities (finance/coding) — читает тот же blackboard, не ломая модель.

Это и есть **Stigmergy** (ADR-103): агенты координируются через оставленные в blackboard «метки», а не через прямые вызовы.

---

## 4. Consequences

**Плюсы:**
- Decoupling: агенты не знают друг о друге (только о scope).
- Детерминизм (I-09): version+seq → воспроизводимый порядок.
- Нет lost updates (single-writer + contention-raise, без локов).
- Audit: append-only trail всех шагов задачи.

**Минусы / ограничения:**
- In-memory (Wave C1): не персистится между перезапусками ядра. Persist + resume — Wave C5 (отложено, product-mode).
- Single-writer-per-scope: двум агентам нельзя дописывать один scope параллельно под разными writer-ами → caller решает (snapshot + re-append под своим id, или отказ). Для последовательных pipeline (Planner→Research→Architect→Programmer→Writer) это не проблема.
- `BlackboardContention` требует обработки caller-ом (retry/skip) — не скрыт внутри blackboard.

---

## 5. Почему не альтернативы

- **Прямые вызовы агент→агент:** нарушает K1/K6 и ADR-103 (god-object, tight coupling).
- **Shared mutable dict без single-writer:** lost updates при параллельной записи.
- **EventBus для всего:** события — для сигналов/жизненного цикла; blackboard — для состояния задачи (разные оси, оба нужны).
