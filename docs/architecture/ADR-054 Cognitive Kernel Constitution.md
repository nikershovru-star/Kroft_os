---
id: ADR-054
title: "Cognitive Kernel Constitution — v2.0 immutable invariants"
status: accepted
evidence_level: V
date: "2026-08-02"
decision_score: 0.95
confidence: high
risk: high
related: [TZ-015, TZ-016, TZ-017, TZ-018, TZ-019, TZ-020, TZ-021, TZ-022, TZ-023, ADR-043, ADR-044, ADR-045, ADR-046, ADR-047, ADR-048, ADR-049, ADR-050, ADR-051, ADR-052, ADR-053, Wave-3]
supersedes: [ADR-053 (roadmap — now subordinate), ADR-042 (arch intelligence — now I-15 circuit)]
---

# ADR-054: Cognitive Kernel Constitution (KROFT_OS v2.0)

> **Это не обычный ADR.** Это архитектурная конституция — документ верхнего уровня,
> фиксирующий неизменяемые инварианты системы. Все последующие ADR/RFC/WP обязаны
> ему соответствовать. Нарушение инварианта = архитектурный дефект, ловимый gate (K8).

## 1. Context

За ревью раундов 1–3 концепция Cognitive Kernel существенно уточнена: система
перестаёт быть «набором сервисов» и становится **операционным циклом** (Cognitive
Pipeline как конечный автомат) + 3 сквозных контракта + 1 владелец цикла. Перед
code-фазой TZ-015..023 необходимо зацементировать фундамент, иначе интерфейсы
W3/W4 зафиксируют промежуточную модель и переделка будет дорогой.

Источники (research-grounded):
- Global Workspace Theory для LLM (Anthropic 2026), Zylos 2026, Theater of Mind arxiv 2604.08206.
- OODA loop / Cognitive Decision Loop ORPA (XMPro MAGS 2026) — scored gates, traceability.
- Event Sourcing (Fowler, Azure Architecture) — domain model + replay/audit.
- System 1/2 dual-process (Kahneman); Hard constraints vs soft utilities (constrained optimization).

## 2. The Cognitive Kernel

**Cognitive Kernel** = детерминированное ядро исполнения, живущее и действующее
независимо от внешних LLM. Модели — за contract boundary, взаимозаменяемы,
**необязательны** (есть полный путь исполнения без них).

Первичная сущность — **Cognitive Pipeline как конечный автомат (FSM)**, а не дерево
модулей. Каталог модулей (раунд 1) не исчезает — он становится *реализацией фаз и
контрактов*, а не первичной сущностью.

## 3. INVARIANTS (the Constitution)

Каждый инвариант имеет ID, формулировку, rationale и enforcement (где ловится).

### I-01 — Cognitive Pipeline / State Machine = главный инвариант исполнения
Система исполняется как FSM (§4), а не как произвольная композиция вызовов. Любой
когнитивный путь проходит через определённые состояния с контрактами переходов.
**Enforcement:** arch-gate запрещает прямые вызовы LLM вне Executive/system-1 тиков;
CognitiveKernel FSM — единственный вход в cycle.

### I-02 — Executive = единственная точка управления переходами
Executive — **НЕ фаза цикла**, а **контроллер переходов** (state machine controller).
Он никогда не занимается reasoning. Только: «можно перейти?», «прервать?», «откатить?»,
«повторить?». Именно Executive — владелец цикла и **enforcement-точка LLM-free core**:
решает, когда LLM, когда правила (по бюджету/доступности).
**Enforcement:** gate запрещает переходы состояний вне Executive.

### I-03 — Decision Engine = отдельный этап выбора действий
Planner предлагает кандидатов (множество). Decision выбирает ОДИН по multi-criteria
(risk/cost/time/confidence/policy/resources) — expected-utility selection. Финальный
выбор **детерминирован по policy** (rule/policy-based), LLM — только советник
(оценка риска), не селектор. Без этого Decision вырождается в «спросим модель».
**Enforcement:** Decision.select — pure deterministic (нет LLM-вызова внутри).

### I-04 — Intent = источник целей
Все цели происходят из Intent (пользователь / внешний сигнал / scheduled goal).
Нет самопорождаемых целей вне Intent + Value System. Intent несёт ConfidenceScore.

### I-05 — Attention = когнитивный селектор контекста
Attention отвечает «что посмотреть» (focus of processing), параметризуется Intent/
World State. **НЕ** управляет бюджетами — это отдельный модуль (I-06). Сохраняем
термин Attention (точнее отражает когнитивную роль).
**Enforcement:** Attention не импортирует ResourceManager (разделение запрос→квота).

### I-06 — Resource Manager = управление вычислительными ресурсами (отдельно от Attention)
Cognitive Resource Manager = enforcement бюджетов/квот/scheduling: CPU, токены,
вызовы LLM, память, поиск, кол-во агентов. Детерминирован, часть LLM-free core.
Attention **запрашивает** квоту у ResourceManager («можно подтянуть 200 узлов?»),
тот разрешает/урезает. Слияние в один god-module = нарушение K3 (слабая связность).
**Enforcement:** gate запрещает объединять Attention+ResourceManager в один класс.

### I-07 — World State = единственный источник истины локального узла
Локальный World State — SSOT для узла. Все фазы читают/пишут через него. Partial
observability допустима (perception loop обновляет).
**Enforcement:** domain-сущности не хранят «истину» вне WorldState (через порт).

### I-08 — Shared Context = федеративная проекция World State
Shared Context (Wave 3 / TZ-022) = проекция World State для федерации. Не копия, а
выборочно опубликованная часть (selective sharing, default DENY).
**Enforcement:** sync только permitted subgraph (grant required).

### I-09 — LLM-Free Core = обязательный путь исполнения
Существует **system-1** (реактивный) путь: Perception → Attention → (rule/LLM-free)
→ Execution — **без вызова модели**. Полный deliberative (system-2) идёт через все
фазы. Ядро живёт и действует без моделей; модели ускоряют/советуют.
**Enforcement:** system-1 path не содержит LLM-вызовов (gate проверяет).

### I-10 — Contract Boundary между ядром и моделями
Модели за границей (ILlm-порт). Взаимозаменяемы, необязательны. Ядро не импортирует
конкретную модель. **K1/K8** соблюдены.

### I-11 — Hard Constraints > Soft Utilities
Value System двухслойная: (a) **hard constraints (veto)** — то, что нельзя
перевесить (K1 Contracts First, безопасность, инварианты ядра); читаются из Normative
Memory; вариант, нарушающий — отбрасывается ДО оценки. (b) **soft utilities (weights)**
— торг между clarity/speed/cost. Без разделения «исполняемые ценности» превратятся в
«жертвуем контрактами ради скорости».
**Enforcement:** ValueSystem.evaluate отбрасывает hard-violating кандидатов первыми.

### I-12 — ConfidenceScore = единый контракт всех когнитивных сущностей
Confidence не только в World State, а **везде**: Intent, Memory-запись, Reasoning-вывод,
Plan, Decision. Контракт `ConfidenceScore`:
- `value: float` (0..1);
- `provenance`: наблюдение / вывод модели / вывод правила / агрегация;
- `calibration`: epistemic (не знаю — доучить) vs aleatoric (шум мира);
- `aggregation_rule`: как confidence плана выводится из шагов (min/product/weighted).
Отдельный ADR-уровня контракт (ADR-055).
**Enforcement:** все domain-сущности несут ConfidenceScore (typing/test).

### I-13 — Provenance для каждого когнитивного артефакта
Каждый артефакт (Intent/Plan/Decision/Memory/Knowledge) имеет provenance: откуда,
кем (rule/model/agent), когда. Обязательно для replay/audit/federation.
**Enforcement:** domain-сущности имеют `provenance` (typing/test).

### I-14 — Learning изменяет систему только через Policy + Commit
Reflection → Learning → **Knowledge Proposal** → **Policy Check** → **Commit** → Memory.
Learning **предлагает** изменения, не пишет напрямую. Executive + Policy + Normative
Memory принимают. Решение «создать правило/ADR/норму» — только при confidence > порог
+ повторении (низко-уверенный единичный опыт ≠ норма).
**Enforcement:** Learning не вызывает Memory.write напрямую (через ILearningPolicy).

### I-15 — Cognitive Reflection и Runtime Reflection = разные контуры
Cognitive Reflection — в когнитивном тике (улучшение reasoning/plan); Runtime
Reflection — в adaptive/system-тике (эволюция policy/норм, ADR-042 L5/L6/L7).
Два независимых контура, не смешивать.
**Enforcement:** не импортировать arch-intelligence в когнитивный тик (K8 локально).

### I-16 — Dual-process (system-1 / system-2)
Не каждый тик идёт через полный Reasoning→Planning→Decision. system-1 (реактивный,
LLM-free) vs system-2 (deliberative). Это даёт реактивность + реализует I-09.
**Enforcement:** CognitiveKernel поддерживает оба пути (тип тика).

### I-17 — Каждый переход воспроизводим и журналируется (Event Semantics)
Каждый переход FSM: имеет контракт, условия, может быть прерван Executive, может
откатиться, **логируется**, **воспроизводим** (event log → replay/audit/federation).
События: ObservationReceived, GoalCreated, GoalCancelled, PlanGenerated, DecisionAccepted,
DecisionRejected, ExecutionStarted, ExecutionFinished, ReflectionCompleted, PolicyUpdated
(§6). **Enforcement:** FSM эмитит события в EventBus (reuse TZ-015).

### I-18 — Domain Model = первоклассные неизменяемые сущности
Intent, Goal, Plan, Decision, Observation, Episode, Policy, WorldState, Action, Skill —
первоклассные доменные сущности (frozen dataclasses), а не dict. Иначе через год —
словари Python.
**Enforcement:** domain-модуль с frozen-сущностями; мутации через FSM (K8).

### I-19 — Value System = исполняемая оценочная функция (KROFT Laws как ценности)
KROFT Laws (K1..K8) — не плакат, а исполняемые ценности системы. Hard layer (I-11a)
читается из Normative Memory; soft layer (I-11b) торгуется. Value System = objective/
evaluation fn, Decision Engine = selector по ней. Пара.
**Enforcement:** ValueSystem реализует K1..K8 как hard/soft (test).

### I-20 — Self-Evolving within immutable kernel invariants (guardrail)
Self-Evolving Cognitive Operating System = эволюция **policy / стратегий / навыков /
soft-utilities** при **неизменном ядре** (pipeline-инвариант, LLM-free core, hard
constraints, контракты). Не эволюционирует то, что инвариант. Формула цели:
«Self-Evolving within immutable kernel invariants». Без guardrail I-20 «self-evolving»
вступит в противоречие с O1 «ядро неизменно».
**Enforcement:** LearningPolicy меняет только soft/Normative-политики, не I-01..I-19.

## 4. Cognitive FSM (states)

```
        ┌──────────────────────────────────────────────────────────┐
        │                     EXECUTIVE CONTROLLER                    │
        │         (sole transition authority; I-02; LLM-free)        │
        └──────────────────────────────────────────────────────────┘
                              ↑ controls ↓
  Idle ─▶ Observe ─▶ Orient ─▶ Deliberate ─▶ Commit ─▶ Execute ─▶ Evaluate ─▶ Learn ─┐
   ▲                                                                                 │
   └─────────────────────────────────────────────────────────────────────────────────┘
```
- **Idle**: ждёт Intent.
- **Observe**: получает Observation (факт), обновляет World State (I-07).
- **Orient**: Attention (I-05) + ResourceManager (I-06) → Context Assembly.
- **Deliberate**: Reasoning → Planning (TZ-016) → Decision (I-03). system-1 shortcut
  минует Deliberate (I-16).
- **Commit**: DecisionAccepted → Policy Check (I-11/I-14) → готовность к Execution.
- **Execute**: запуск агента/действия (через IAgentPlatform, I-10).
- **Evaluate**: Observation результата, сверка с World State, ConfidenceScore (I-12).
- **Learn**: Reflection (I-15 cognitive) → Learning (I-14) → Knowledge Proposal →
  Policy Check → Commit → Memory Update.
- Каждый переход: контракт + условия + прерываемость Executive + лог + воспроизводимость (I-17).

## 5. Core Cognitive Domain (first-class entities, frozen)

`Intent, Goal, Plan, Decision, Observation, Episode, Policy, WorldState, Action, Skill,
ConfidenceScore, Provenance, CognitiveEvent` — все frozen dataclasses в `kernel/domain/`
(K1). Мутации только через FSM (I-18).

## 6. Event Semantics (CognitiveEvent types, I-17)

`ObservationReceived, GoalCreated, GoalCancelled, PlanGenerated, DecisionAccepted,
DecisionRejected, ExecutionStarted, ExecutionFinished, ReflectionCompleted, PolicyUpdated`
— каждое событие несёт `provenance` (I-13) + `confidence` (I-12). Эмитятся в EventBus
(reuse TZ-015 TcpEventBus). Обеспечивают replay / audit / debugging / federation / dist-exec.

## 7. Cross-cutting Contracts (сквозные)

1. **ConfidenceScore** (I-12) — ADR-055.
2. **ValueSystem** (I-11/I-19) — hard veto (Normative) + soft utilities (K1..K8).
3. **ResourceManager** (I-06) — запрос/квота, отдельно от Attention; part of LLM-free.
4. **LearningPolicy** (I-14) — стратегия фазы Learning, не сервис; polymorphic по слою
   памяти (эпизод vs норма).

## 8. LAW Compliance

- **K1**: kernel импортирует только contracts + stdlib (FSM, domain в kernel/domain).
- **K3**: модульность — Attention ≠ ResourceManager (I-05/I-06); Executive ≠ phase (I-02).
- **K5**: design-first; Learning меняет только через Policy+Commit (I-14); selective
  sharing default DENY (I-08).
- **K6**: узлы через порты (IEventBus/ICrdtGraph/ILlm/IAgentPlatform).
- **K8**: services/adapters НЕ импортируют kernel/runtime; Cognitive Reflection ≠
  Runtime Reflection (I-15).

## 9. Relationship to existing docs

- **ADR-053** (roadmap): теперь **подчинён** ADR-054 — слои реализуют фазы/контракты.
- **ADR-044..052** (TZ-015..023): порты остаются; интерфейсы обновляются под
  ADR-055 (ConfidenceScore) и CognitiveKernel FSM (см. Compatibility Matrix).
- **ADR-042** (Arch Intelligence): теперь = I-15 Runtime Reflection circuit.
- **ADR-043** (WP-14): CrdtGraphEngine/RaftLiteElector/TcpEventBus = substrate для
  WorldState/SharedContext/Event Semantics.

## 10. Validation

- До code: ad-hoc verify AKB consistency (ADR-054 accepted, invariants enumerated).
- После code (code-фаза TZ): каждый инвариант покрыт gate-тестом (K8 negative tests).
- `tools/akb_lint.py` включает проверку ADR-054 accepted.
