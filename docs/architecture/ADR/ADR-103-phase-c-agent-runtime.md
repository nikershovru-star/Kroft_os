# ADR-103 — Phase C: Agent Runtime (мультиагентная система на существующем substrate)

- **Status:** proposed (revised per reviewer audit 2026-08-06)
- **Date:** 2026-08-06
- **Addresses:** этап «Phase C» — превратить существующих агентов (Research / Architect / Programmer / Writer / Planner / Finance) в рабочую мультиагентную систему. **Без создания новых специализированных агентов.**
- **Supersedes / Relates:** ADR-102 (Agent Behaviour Layer), ADR-037 (Agent Orchestration & Self-Analysis), ADR-072/073 (Identity & Trust), ADR-074 (Procedural memory — Skills), ADR-046 (Long-Term Memory Evolution), ADR-034 (Approval Workflow), ADR-030 (Policy Boundary), ADR-013 (Workflow Platform), RFC-009 (Multi-Agent Orchestration), RFC-010 (Supervisor & Recovery).
- **Reviewer audit:** 2026-08-06 — 10 пунктов (god-object / thread-safety / deadlock / idempotency / scalability / approval-security / K6 / SOLID / event-driven / debt). Все применены, см. §13.

---

## 1. Context & Problem

Agents v0.1 (ADR-102) дал 6 агентов, каждый = реализация `IAgentPlatform`/`IAgentExecutor`, подключённая через `MultiAgentExecutor` на `Orchestrator.dispatch(capability=...)`. Это **точечная маршрутизация**: один запрос → один агент → ответ. Между агентами нет координации, общего состояния, делегирования, ревью, обучения и точек человеческого одобрения.

Phase C превращает этот набор в **Agent Runtime** — систему, где агенты совместно решают задачу: планируют, делят на подзадачи, исполняют через пайплайны, обмениваются контекстом через Shared Memory, делегируют, проходят review-loop, накапливают навыки, учатся на исходах и останавливаются на Human Approval Points.

**Жёсткие ограничения (из задачи + аудита):**
- НИКАКИХ новых специализированных агентов.
- **НЕ** god-object: координация разбита на фокусные координаторы за портами; `AgentRuntime` — тонкий facade; композиция — только в composition root.
- **НЕ** прямые вызовы агентами друг друга: контекст только через blackboard / `IEventBus`.
- Закладываем устойчивость (versioned blackboard, idempotency, cycle-detection, partitioned bus) СРАЗУ в Wave C1–C2, не как долг.

---

## 2. Research Synthesis (внешние архитектуры)

Источники: Microsoft AutoGen (v0.4, group chat / FSM speaker transition), LangGraph (StateGraph + checkpointer + `interrupt()`/HITL), CrewAI (role/goal/backstory + sequential/hierarchical + manager-worker), OpenAI Agents SDK (handoffs + guardrails + tracing), Microsoft Semantic Kernel / Agent Framework (plugins + function-calling + A2A), blackboard/stigmergy, event-driven durable execution, Reflexion / self-evolving, agent memory architecture.

| Паттерн | Источник | Оценка | Применимость к KROFT |
|---|---|---|---|
| Group Chat / speaker selection | AutoGen | ✅ координация, но state фрагментируется по history | Нужен отдельный Shared State (blackboard) |
| Shared spec/state (blackboard) | AutoGen #7144, stigmergy | ✅✅ −80% токенов, debuggable, traceable | `IBlackboard` (новый фокусный порт) |
| Stigmergy (env как посредник) | Reddit/arXiv 2661.08129 | ✅ асинхронность, нет ожидания ответа | EventBus + blackboard уже есть |
| FSM speaker transition | AutoGen FSM | ✅ детерминизм переходов | `Workflow` (frozen steps) покрывает |
| HITL via `interrupt()` + checkpointer | LangGraph | ✅✅ pause/resume | `IApprovalGate` (новый порт) + ADR-034 |
| Hierarchical (manager delegates) | CrewAI | ⚠️ эффективно, но **зацикливания** | Нужен delegation-DAG + cycle detection |
| Handoffs (pass control) | OpenAI Agents SDK | ✅ просто, но flaky если не sequential | `IDelegationService` (capability-index, не перебор) |
| Plugins / function-calling | Semantic Kernel | ✅ навыки = функции | `ADR-074 Skills` покрывает |
| A2A protocol | Google/Microsoft | ✅ федерация, вне scope v0.1 | `ADR-075` (позже) |
| Reflexion (verbal RL) | Self-evolving survey | ✅✅ кросс-прогонное обучение | `IMemoryEvolution` (ADR-046) |
| Event-driven durable exec | AWS/Confluent | ✅ отказоустойчивость, backpressure | `IEventBus`/`TcpEventBus` |
| Memory: short/long/team + compaction | Anthropic/RedHat | ✅✅ compaction + write-back | `ILayeredMemory` + ContentIndex |

**Анти-паттерны (из research):** state only в message-history → невозможен trace/retry; hierarchical без max-iterations → зависание; полная консистентность (locks) → избыточна; handoffs не по порядку → race; нет compaction → context pollution.

---

## 3. Existing Substrate (K5 mapping)

### 3.1 Уже переиспользуемое (НЕ дублируем)
| Пункт Phase C | Компонент | Файл / ADR |
|---|---|---|
| WorkflowEngine | `Workflow`/`Step` (frozen, copy-on-write), `WorkflowExecutor`, `WorkflowStatus` | `contracts/i_workflow.py`, `services/workflow_executor.py`, ADR-013 |
| Pipeline / routing | `MultiAgentExecutor` (capability→executor), `Orchestrator.dispatch` | `services/multi_agent_executor.py`, `kernel/orchestrator.py` |
| Shared Memory (база) | `ILayeredMemory`, `InMemoryLayeredMemory`, `ContentIndex`, graph | `contracts/i_memory.py`, `services/memory_platform.py` |
| Context Exchange (сигналы) | `IEventBus` / `TcpEventBus` (pub/sub + history) | `contracts/i_event_bus.py`, `adapters/tcp_event_bus.py` |
| Task Delegation (база) | `Orchestrator.dispatch(capability, trust)`, trust scoring | `kernel/orchestrator.py`, ADR-073 |
| Review Loop (база) | `ADR-037 Self-Analysis`, `SupervisorFailover` | ADR-037, `services/supervisor_failover.py` |
| Skill System | `ADR-074 Procedural memory — Skills`, `in_memory_learning_store` | ADR-074, `adapters/in_memory_learning_store.py` |
| Learning | `IMemoryEvolution` (consolidate/forget/supersede) | `contracts/i_memory_evolution.py`, ADR-046 |
| Metrics | `InMemoryTelemetry`, event-driven alerting | `adapters/in_memory_telemetry.py`, ADR-040 |
| Human Approval (база) | `IPolicy` + `PolicyContext`/`PolicyDecision`, ADR-034/030 | `contracts/i_policy.py`, ADR-034/030 |

### 3.2 НОВЫЕ фокусные порты (по аудиту — SRP, не god-object)

> **Дисциплина объявления портов (reviewer fix #1):** порт объявляется и реализуется ТОЛЬКО в той волне, где появляется реальная реализация. Порт без реализации = долг, а не актив. Поэтому Wave C1 несёт только 3 порта; остальные объявляются в своих волнах.

**Wave C1 (фундамент):**
| Порт | Ответственность (SRP) |
|---|---|
| `IAgentRuntime` | **Тонкий facade**: единая точка входа `run_workflow(goal)`, делегирует координаторам. Без оркестрационной логики. |
| `IBlackboard` | Versioned/append-only координационное состояние задачи: `append(scope, agent_id, payload)→version`, `snapshot(scope)→(payload,version)`. Single-writer per scope. **НЕ память агента.** |
| `IDelegationService` | Delegation-DAG: назначает исполнителя по capability-индексу, **cycle detection + max depth**, trust-delta. |

**Позднее (объявить в своей волне, когда появится реализация):**
| Порт | Волна | Сценарий |
|---|---|---|
| `IWorkflowCoordinator` | C2/C3 | когда нужна сборка Workflow из goal + выбор стратегии |
| `ICoordinationStrategy` (Stigmergy + слоты Sequential/Hierarchical) | C1 объявить Stigmergy; остальные — слоты, реализовать при реальном сценарии | Stigmergy выбран как базовый паттерн C1; Sequential/Hierarchical — только если появится сценарий, требующий их |
| `IReviewLoop` | C5 | когда появится cross-review цикл |
| `IApprovalGate` | C6 | когда появится human-approval точка |

Это устраняет избыточную абстракцию на уровне контрактов (не объявлять порты раньше реализации).

---

## 4. Decision / Architecture (по 10 пунктам, с учётом аудита)

### 4.1 Multi-Agent Workflow Engine
- Задача = `Workflow` (frozen `Step`, ADR-013). `IWorkflowCoordinator` строит workflow, биндит шаги к capability, выбирает стратегию (`ICoordinationStrategy`).
- Движок = `WorkflowExecutor` (переиспользуется). **Координационная логика вынесена в стратегии, не в runtime.**
- `Step` расширяется полем `idempotency_key` (JSON-native uuid-строка, НЕ timestamp — соблюдает ADR-013) и флагом `idempotent: bool`.
- **Termination:** `max_steps` + `max_review_cycles` (анти-паттерн CrewAI).

### 4.2 Agent Pipeline
- Через `MultiAgentExecutor` (capability→executor). Типы пайплайна = **стратегии** (`ICoordinationStrategy`).
- **Wave C1: только Stigmergy (reviewer fix #3).** Stigmergy выбран как базовый паттерн C1: агенты пишут в blackboard и читают snapshot, без прямого вызова друг друга. `SequentialStrategy` / `HierarchicalStrategy` — **слоты в `ICoordinationStrategy`**, НЕ реализуются в C1. Реализовывать их, только когда появится реальный сценарий, требующий sequential/hierarchical (Open/Closed: интерфейс готов, реализация — по требованию).
- **Open/Closed:** новый тип пайплайна = новый strategy-класс, правки runtime НЕТ.

### 4.3 Shared Memory → **Versioned Blackboard** (фикс аудита #2)

> **ГРАНИЦА `IBlackboard` ≠ `ILayeredMemory` (reviewer fix #2, arch-gate criteria):**
> - `IBlackboard` — **координационное состояние задачи**: что нужно ДРУГИМ агентам для координации (промежуточные результаты шагов, статусы, handoff-сигналы). Versioned, single-writer per scope, TTL.
> - `ILayeredMemory` — **память агента** (долгосрочная семантика, эпизоды, навыки).
> - **Критерий для arch-gate:** в blackboard пишется ТОЛЬКО то, что нужно другим агентам для координации; всё остальное (личный контекст агента, рефлексия, обучение) — в `ILayeredMemory`. Если сервис пишет личный контекст агента в blackboard ИЛИ координационный handoff в `ILayeredMemory` вместо blackboard — arch-gate ЛОВИТ (детектор: импорт обоих портов в одном координаторе без разделения scope, либо запись `agent.<id>.scratch` в blackboard-team-scope).
> - Реализация `IBlackboard` НЕ наследует и НЕ импортирует `ILayeredMemory`; это отдельный port (K5/K6).

- `IBlackboard` (append-only, versioned): пишет иммутабельные записи с монотонным `version` (логический ординал, не wall-clock). Читатели получают `snapshot(scope)` на версию → **нет lost updates без блокировок**.
- **Single-writer per scope**: scope (напр. `team.state`) пишется одним владельцем за раз; конкурентная запись → отклоняется (или CAS по version). Это устраняет не-thread-safe `InMemoryLayeredMemory` для разделяемого состояния.
- Скоупы: `agent.<id>.scratch` (приватный, в `ILayeredMemory`) и `team.state` (общий blackboard). Разделение предотвращает перезапись.
- TTL для горячего состояния + periodic compaction → Long-Term (Anthropic/RedHat). **Eventual consistency, НЕ транзакции.**

### 4.4 Agent Context Exchange → **stigmergy, не broadcast** (фикс аудита #5/#9)
- **Правило (hard):** агенты НЕ вызывают друг друга напрямую. Контекст — только через `IBlackboard` (чтение snapshot) + `IEventBus` (lifecycle-сигналы: `agent.<cap>.done`, `workflow.step.<id>`).
- `IEventBus` используется для **сигналов**, blackboard — для **состояния**. Для контекста между агентами — blackboard (stigmergy), НЕ broadcast-сообщения (масштаб: broadcast → message storm при 20–100 агентах).

### 4.5 Task Delegation → **Delegation-DAG + cycle detection** (фикс аудита #3/#5)
- `IDelegationService` ведёт DAG родитель→ребёнок. Перед делегированием: (a) проверка цикла (ребёнок не должен делегировать предку → A→B→A блокируется); (b) `max_depth`.
- Speaker selection = **capability-индекс** (O(1), уже в `Orchestrator`), НЕ O(n) перебор.
- Исход → `TrustRegistry.record_outcome` → trust эволюционирует (ADR-073/102).
- Planner (существующий) генерирует план; делегирование — через `IDelegationService`, НЕ новый агент-manager.

### 4.6 Agent Review Loop → **idempotent retry + failover** (фикс аудита #4)
- `IReviewLoop`: execute → review (кросс-агент, по ADR-037) → accept | reject→replan→re-execute. `max_review_cycles`.
- **Idempotency:** retry (via `SupervisorFailover`) ТОЛЬКО для шагов `idempotent=True` с `idempotency_key`. Неидемпотентные шаги не ретраятся (избегаем double-effect).
- Failover на агента той же capability при сбое.

### 4.7 Agent Skill System
- Навыки = процедуры агентов (ADR-074). Агент запечатывает решённую подзадачу в `in_memory_learning_store`; discovery по capability/тегу.
- **Boundary:** только SOFT-процедуры (O1, ADR-046).

### 4.8 Agent Learning
- `IMemoryEvolution.consolidate(episodes)` → `SemanticFact`/`Policy` (SOFT). Reflexion: вербальная рефлексия в blackboard → консолидация.
- **Guard:** HARD-слой НЕ эволюционирует (`IValueSystem.hard_violations` реджектит).

### 4.9 Agent Metrics
- `InMemoryTelemetry` + события: `agent.start/done/fail`, `review.cycle`, `delegation.trust_delta`, `skill.learned`, `approval.gate`. KROFT Desktop (ADR-100) показывает.

### 4.10 Human Approval Points → **async gate, default-deny, audit** (фикс аудита #1/#6)
- `IApprovalGate.approve(point, context)` возвращает `pending` + correlation_id **немедленно** (НЕ блокирует event loop). Резолюция приходит асинхронно через `IEventBus`.
- **TTL + default-deny:** если человек не ответил в TTL → `denied` (НЕ livelock ожидания).
- **Non-bypassable:** approval — отдельный gate-step в workflow; обход невозможен (PolicyEngine + gate-step в графе).
- **Audit:** каждое решение (allow/deny) пишется в `IActionLog` (ADR-034). Воспроизводимость.
- Точки: до «опасной» делегации (Policy Boundary), после review при низком trust, перед записью skill в Long-Term, перед внешним side-effect (Finance→exchange, out-of-scope v0.1).

---

## 5. Constraints (LAW K1–K8 + аудит)

- **K1:** все новые порты — `contracts/*` + stdlib.
- **K5:** reuse существующего (§3.1); новые порты (§3.2) — фокусные, по одной оси каждый (SRP).
- **K6 (аудит #7):** `services/agent_runtime.py` (facade) импортирует **исключительно контракты-порты**. Конкретные координаторы и их wiring — в `composition/` (composition root). Если facade потянет конкретный сервис → нарушение (arch-gate поймает).
- **K8:** тесты в `tests/agent_runtime/`.
- **SRP (аудит #1):** `AgentRuntime` = facade, НЕ god-object. Оркестрация — в `IWorkflowCoordinator`/`IDelegationService`/`IReviewLoop`/`IApprovalGate`.
- **Open/Closed (аудит #8):** координационные стратегии — объекты `ICoordinationStrategy`, не if-ветки.
- **Event-driven (аудит #9):** агенты не вызывают друг друга напрямую.
- **O1:** Learning НЕ трогает HARD-слой. **I-09:** LLM везде опционален.

---

## 6. Recommended Interfaces (порты)

Новые (фокусные, §3.2): `IAgentRuntime`, `IWorkflowCoordinator`, `IDelegationService`, `IReviewLoop`, `IApprovalGate`, `IBlackboard`, `ICoordinationStrategy`. Каждый — только порт (без имплементации в `contracts/`).

Конкретные реализации (services/*) и композиция — в composition root. `AgentRuntime` зависит только от этих портов.

> K5-примечание: это расширяет предыдущую версию ADR (где портов планировалось 0). Аудит обоснованно потребовал фокусных портов вместо god-object — это K5-совместимо (port-per-boundary).

---

## 7. Anti-patterns (защита)

1. **God-object** (аудит #1): один runtime-файл композирует всё → SRP нарушен. *Fix:* facade + фокусные координаторы за портами.
2. **Lost updates** (аудит #2): `InMemoryLayeredMemory` не thread-safe. *Fix:* `IBlackboard` append-only + version + single-writer.
3. **Delegation cycle / livelock** (аудит #3): A→B→A. *Fix:* DAG + cycle detection + max depth; approval async default-deny.
4. **Non-idempotent retry** (аудит #4): retry портит side-effects. *Fix:* idempotency-key, retry только idempотентных.
5. **Message storm / O(n) selection** (аудит #5): broadcast + перебор. *Fix:* stigmergy blackboard + capability-index + partitioned bus.
6. **Bypassable/blocking approval** (аудит #6): approval блокирует loop. *Fix:* async gate-step, TTL, default-deny, audit.
7. **Direct agent calls** (аудит #9): агенты вызывают друг друга. *Fix:* только blackboard/EventBus.
8. **Strategy in if-branches** (аудит #8): *Fix:* `ICoordinationStrategy` объекты.

---

## 8. Risks (с митигациями из аудита)

- **R1 race на shared state** → `IBlackboard` versioned/single-writer.
- **R2 delegation cycle/livelock** → DAG + cycle detection + max depth + approval default-deny.
- **R3 approval блокирует long-run** → async gate + TTL (non-blocking event loop).
- **R4 over-forget в learning** → consolidate только повторяющиеся high-confidence (ADR-046).
- **R5 scale 20–100 агентов** → stigmergy (не broadcast) + partitioned bus + capability-index. Multi-machine: `ITcpEventBus` с discovery + consistent-hashing по topic (Wave C5+, интерфейс заложен).

---

## 9. Testing Strategy

- **K8 contract:** `MultiAgentExecutor` роутит N capability (расширить).
- **Workflow reproducibility:** тот же frozen `Workflow` + input → тот же результат (ADR-013 DoD).
- **Blackboard versioned:** concurrent append → версии монотонны, snapshot консистентен, single-writer reject concurrent write.
- **Delegation DAG:** A→B→A отклоняется; превышение max_depth отклоняется; capability-индекс O(1).
- **Idempotency:** retry идемпотентного шага по idempotency-key = один эффект; неидемпотентный НЕ ретраится.
- **Review termination:** `max_review_cycles` (не бесконечный).
- **Approval:** gate возвращает `pending` немедленно; TTL-EXP → `denied`; решение в `IActionLog`; обход gate-step невозможен.
- **Strategy Open/Closed:** новый strategy-класс добавляется без правки runtime (тест подтверждает).
- **Event-driven rule:** тест запрещает прямой вызов агента агентом (только через порты).
- **Negative (arch-gate):** `services/agent_runtime.py` импортирует только contracts; новые порты — в `contracts/`.

---

## 10. Honest Assessment

- **Готовность substrate:** workflow/memory/event-bus/policy/trust/skills/learning/metrics — есть. **Gap после аудита:** нужны фокусные координаторы (§3.2) вместо god-object, versioned blackboard, delegation-DAG, async approval-gate, strategy-объекты.
- **Реальный объём:** не «новый framework», а 7 маленьких портов + composition root + тонкий facade. Это KROFT-native.
- **Риск:** оркестрационная сложность (race/cycle/blocking) адресуется явно в §4 и §7.
- **Не делаем:** новых агентов, нового framework, прямых вызовов агентов, блокирующих approval.

---

## 11. Implementation Plan (tight scope, долги заложены в C1–C2)

- **Wave C1 — ФУНДАМЕНТ (tight scope, только реализуемое):**
  - `contracts`: `IAgentRuntime` (facade), `IBlackboard` (versioned, single-writer), `IDelegationService` (DAG + cycle detection + max depth).
  - `IBlackboard` impl: append-only versioned + `snapshot(scope)`; single-writer per scope (конкурентная запись отклоняется).
  - `IDelegationService` impl: capability-index выбор; DAG-трекинг родитель→ребёнок; проверка цикла (A→B→A) + max_depth.
  - `AgentRuntime` facade: `run_workflow(goal)` → делегирует `IDelegationService` + blackboard; **композиция только в composition root**.
  - `ICoordinationStrategy` интерфейс + **только `StigmergyStrategy`** (остальные — слоты).
  - ОДИН сквозной тест: задача → делегирование A→B → обмен через blackboard → результат; + proof-of-fire на cycle-detection (A→B→A блокируется).
  - arch-gate: services/agent_runtime импортирует только contracts; boundary `IBlackboard`≠`ILayeredMemory` (критерий §4.3).
- **Wave C2 — Workflow binding + Strategies — DONE (2026-08-06):** `IWorkflowCoordinator` (сборка Workflow из goal, deterministic sha256), выбор `StigmergyStrategy`; wiring в composition root `run_kroft --agent-runtime` (default OFF).
- **Wave C3 — Trust + Metrics:** delegation trust-delta, telemetry-события.
- **Wave C4 — Strategies (late):** Sequential/Hierarchical — ТОЛЬКО если сценарий потребует.
- **Wave C5 — Review Loop + Partitioned bus:** `IReviewLoop` (cross-review + `max_review_cycles` + idempotent retry); EventBus topic-partitioning + consistent-hashing для multi-machine.
- **Wave C6 — Approval Gate:** `IApprovalGate` async + TTL + default-deny + audit `IActionLog`.
- **Wave C5-late — Multi-machine:** `ITcpEventBus` discovery + consistent-hashing по topic.

Каждый wave — атомарный коммит, arch-gate green, full-suite green. **Фундамент Phase C считается состоявшимся, если Wave C1 проходит gate БЕЗ god-object и БЕЗ прямых вызовов между агентами.**

---

## 12. Decision

**Принять Phase C** как композицию существующего substrate через **тонкий `AgentRuntime`-facade** + **фокусные координаторы за портами** (`IWorkflowCoordinator`, `IDelegationService`, `IReviewLoop`, `IApprovalGate`, `IBlackboard`, `ICoordinationStrategy`). Без новых специализированных агентов. Без god-object. С versioned blackboard, delegation-DAG, idempotency, async approval-gate, strategy-объектами. Долги (single-writer blackboard / idempotency / cycle-detection / partitioned bus) заложены в Wave C1–C2. K1/K5/K6/K8/O1/I-09 + SRP/Open-Closed/event-driven соблюдены.

---

## 13. Reviewer Audit Response (2026-08-06) — 10 fixes applied

| # | Аудит | Применено в ADR-103 |
|---|---|---|
| 1 | God Object | §4/§5/§6: `AgentRuntime`=facade; оркестрация в `IWorkflowCoordinator`/`IDelegationService`/`IReviewLoop`/`IApprovalGate`; композиция в composition root. |
| 2 | Thread-safe Shared Memory | §4.3: `IBlackboard` append-only versioned + single-writer per scope + snapshot; заменяет прямое использование не-thread-safe `InMemoryLayeredMemory` для разделяемого состояния. |
| 3 | Deadlock/livelock | §4.5: `IDelegationService` DAG + cycle detection + max depth; §4.10: approval async + TTL + default-deny (нет livelock ожидания). |
| 4 | Fault tolerance / idempotency | §4.1/§4.6: `Step.idempotency_key` + `idempotent`; retry только идемпотентных через `SupervisorFailover`. |
| 5 | Scalability | §4.4/§4.5: stigmergy blackboard (не broadcast) для контекста; capability-index O(1) selection; §8 R5 + Wave C5: partitioned bus + consistent-hashing для multi-machine. |
| 6 | Approval security | §4.10: gate-step, TTL, default-deny, non-blocking, audit в `IActionLog`, non-bypassable. |
| 7 | K-laws | §5 K6: facade импортирует только контракты; wiring в composition root; arch-gate ловит нарушение. |
| 8 | SOLID/Clean | §4.2/§5: `ICoordinationStrategy` объекты (sequential/hierarchical/stigmergy), Open/Closed, не if-ветки. |
| 9 | Event-Driven | §4.4/§7: hard rule — агенты не вызывают друг друга; контекст только через blackboard/`IEventBus`. |
| 10 | Debt | §11: single-writer blackboard, idempotency-key, cycle-detection, partitioned bus заложены в Wave C1–C2 (не откладываются). |

---

## 14. Wave C1 — Status: IMPLEMENTED (2026-08-06)

**Фундамент Phase C состоялся.** Без god-object, без прямых вызовов между агентами, K6-clean.

### Созданные артефакты
- **Порты (contracts):** `i_blackboard.py` (`IBlackboard` + frozen `BlackboardEntry`/`BlackboardSnapshot`), `i_delegation.py` (`IDelegationService` + `DelegationDecision`), `i_agent_runtime.py` (`IAgentRuntime` + `WorkflowResult`), `i_coordination_strategy.py` (`ICoordinationStrategy` + `CoordinationStep`, Stigmergy-слот).
- **Сервисы (services, только contracts):** `blackboard.py` (`InMemoryBlackboard` versioned+single-writer), `delegation_service.py` (`DelegationService` DAG+cycle+max_depth), `coordination_strategy.py` (`StigmergyStrategy`), `agent_runtime.py` (`AgentRuntime` facade — делегирует портам, НЕ god-object).
- **Тесты (K8):** `tests/agent_runtime/test_wave_c1.py` (4: end-to-end через blackboard, cycle proof-of-fire A->B->A, versioned single-writer, facade-only-ports), `tests/architecture/test_phase_c_wave_c1.py` (5: K6 на каждый сервис + facade-не-god-object).

### Результаты верификации
- `pytest tests/agent_runtime/test_wave_c1.py` -> **4 passed**.
- `pytest tests/architecture/test_phase_c_wave_c1.py` -> **5 passed** (K6 gate на Wave C1).
- Полный arch-gate -> **22 passed** (было 17, +5).
- `run_kroft --no-demo` стартует (AgentRuntime пока НЕ заинжектен в run_kroft — это Wave C2, composition root).

### Что НЕ сделано (следующие волны, по мере сценариев)
- `IWorkflowCoordinator` (C2), `IReviewLoop` (C5), `IApprovalGate` (C6) — объявить при реализации.
- `SequentialStrategy`/`HierarchicalStrategy` — слоты, не реализованы (аудит #3).
- idempotency-key на `Step` (C2, когда появится retry), partitioned bus (C5-late).
- `AgentRuntime` wiring в `run_kroft` composition root (C2).

---

## 15. Wave C2 — Status: IMPLEMENTED (2026-08-06)

**WorkflowCoordinator + composition root wiring.** Продукт реально использует мультиагентный
контур через `run_kroft --agent-runtime` (default OFF, legacy path неизменен).

### Созданные артефакты
- **Порт (contracts):** `i_workflow_coordinator.py` (`IWorkflowCoordinator`: build_workflow / choose_strategy / run).
- **Сервис (services, только contracts):** `workflow_coordinator.py` (`WorkflowCoordinator` — детерминированная сборка Workflow из goal via sha256, выбор инжектированной StigmergyStrategy, исполнение через IAgentRuntime.delegate_step, copy-on-write Workflow).
- **Composition root:** `run_kroft.py` — `--agent-runtime` (default OFF) инжектит AgentRuntime + InMemoryBlackboard + DelegationService + WorkflowCoordinator(StigmergyStrategy); `interactive_query` маршрутирует через coordinator при флаге.
- **Тесты (K8):** `tests/agent_runtime/test_wave_c2.py` (5: deterministic build_workflow I-09, strategy=stigmergy, end-to-end через run_kroft boot, legacy path unchanged).

### Результаты верификации
- `pytest tests/agent_runtime/test_wave_c2.py` -> **5 passed**.
- Полный arch-gate (без регрессий) -> **22 passed** (C2 не добавлял новых K6-нарушений; services/workflow_coordinator импортирует только contracts, проверено gate).
- `run_kroft --agent-runtime --no-demo` стартует и маршрутизирует через coordinator; без флага — прежний orchestrator path.

### Что НЕ сделано (следующие волны)
- `IWorkflowCoordinator.run` пока 1-step workflow (root capability); multi-step fan-out по DAG — когда появится сценарий (C3/C4).
- `SequentialStrategy`/`HierarchicalStrategy` — слоты (аудит #3).
- `IReviewLoop` (C5), `IApprovalGate` (C6), partitioned bus (C5-late) — по мере сценариев.

---

## 16. Wave C3 — Status: IMPLEMENTED (2026-08-06)

**Delegation trust-delta + telemetry.** Без новых портов (K5 — переиспользованы `ITrustRegistry.record_outcome` + `ITelemetrySink.record`).

### Изменения
- `services/agent_runtime.py`: `AgentRuntime` принимает опц. `trust_registry` + `telemetry`; `delegate_step` ПОСЛЕ исхода вызывает `trust.record_outcome(executor_id, success)` (SOFT, delta=0.1) и `telemetry.record("agent_runtime.delegation", 1.0/0.0, tags={capability, executor})`. Без deps — no-op guard (backward-compat, поведение неизменно).
- `composition/run_kroft.py`: `--agent-runtime` инжектит `trust_registry=self.trust` + `telemetry=InMemoryTelemetrySink()` в `AgentRuntime`.
- `tests/agent_runtime/test_wave_c3.py` (5): success повышает trust (`current_trust`), failure понижает; telemetry-события записаны; без deps поведение неизменно; determinism (I-09).

### Результаты верификации
- `pytest tests/agent_runtime/test_wave_c3.py` -> **5 passed**.
- Полный arch-gate -> **22 passed** (без регрессий; services/agent_runtime импортирует только contracts, включая i_identity/i_telemetry — K6 matrix допускает contracts).
- `run_kroft --agent-runtime --no-demo` стартует с trust+telemetry.

### Что НЕ сделано (следующие волны)
- `IReviewLoop` (C5), `IApprovalGate` (C6), partitioned bus (C5-late) — по мере сценариев.
- Workflow persistence/store для resume/retry (Флаг 2 C2 light — Wave C5+).
- Multi-step планирование goal (Флаг 1 C2 light — Wave C4+).
