---
tags: [kroft, kernel, roadmap, levels, epic, runtime]
created: 2026-07-31
status: draft
version: 2.0
author: Hermes (senior software architect) + Nikita (architecture direction)
depends_on: [ADR-018, ADR-019, Kernel Review (Phase 0.5), Bootstrap Initiative v2 — Master Roadmap]
summary: >-
  12-уровневая дорожная карта развития ядра KROFT_OS + 江市3 недостающих
  архитектурных эпика (Runtime Resource Management / IPC / Capability-Permission).
  Каждый уровень/эпик: Goal / Components / Guardrails (изоляция ядра) / DoD / Smoke.
  Ритм: реализация → арх-аудит → итерация.
---

# KROFT_OS — Master Roadmap v2 (12 Levels + 3 Architecture Epics)

> Статус: **draft** (2026-07-31). Программа развития ядра ПОВЕРХ закрытых 14 волн и
> завершённого Kernel Review (Phase 0.5). Каждый уровень опирается на реальные
> факты из репо (заземлено в Kernel Review): `kernel/kernel.py` УЖЕ реализует
> `Kernel` (FSM + `initialize/start/stop/emit`, владеет `IEventBus`);
> платформы волн 11–14 — **библиотеки** (grep подтвердил: НЕТ lifecycle-методов);
> пакетный import-graph — **DAG без циклов**. Значит уровни 1–3 — это расширение
> СУЩЕСТВУЮЩЕГО, не создание с нуля. Уровни 4–12 и 3 эпика — будущие итерации по
> отдельной команде, с собственным DoD/Guardrails/Smoke (как в Bootstrap Initiative v2).
>
> **Абсолютный принцип (сохранить при всех уровнях):** `Kernel` НЕ импортирует и
> НЕ знает `LLM/Knowledge/Memory/Desktop/API/MCP`. Ядро знает ТОЛЬКО `IServiceLifecycle`
> + `IProcess` + `IEventBus` (шина — собственность ядра, не платформ). Платформы
> попадают в ядро через `ProcessRegistry` (как процессы, не библиотеки).

## Ритм (ваша рекомендация)

После завершения КАЖДОГО крупного уровня (Kernel Foundation / Platform Integration /
Runtime Services / …) — отдельная архитектурная ревизия (как Kernel Review 0.5):
1. Нет ли НОВЫХ циклических зависимостей (пакетный DAG остаётся ацикличным).
2. Не начал ли `Kernel` знать о конкретных платформах (guardrail: только contracts).
3. Не нарушились ли границы слоёв (contracts ↔ adapters ↔ services ↔ kernel).
4. `ProcessRegistry` ли владеет состоянием процессов (не `DependencyContainer`).

Цикл: **реализация → арх-аудит → следующая итерация**.

---

## Уровень 1 — Kernel Foundation (100%)

**Goal.** Ядро, которое можно назвать ОС. Без ручного `agent.ask()`.

**Компоненты (уже реализованы, подтверждено Kernel Review):**
```
Kernel (kernel/kernel.py)         # FSM + start/stop/emit/save
RuntimeState (единый FSM из ADR-019, расширяет LifecycleState)
IEventBus (владеет Kernel, не платформами)
ProcessRegistry (будущий — зарегистрировать процессы из container)
SchedulerService (daemon thread, start/stop)
```

**Guardrails (сохранить):**
- `Kernel` НЕ импортирует `services/agent_platform` и др. платформы — только `contracts.IServiceLifecycle`.
- `IEventBus` принадлежит `Kernel`, платформы лишь `subscribe/publish`.
- Платформы 11–14 не стартуются через `Kernel.start()` (нет у них lifecycle) — они библиотеки, НЕ процессы.

**Definition of Done.**
- `bootstrap.py` (Phase A) → `Kernel.start()` → `Registry.start()` → `Bus.start()`
  → `Scheduler.start()` → `Platforms.start()` → `Runtime Loop` → `Supervisor` → `Shutdown`
  работает БЕЗ ручного `agent.ask()`.
- `Kernel` расширен до единого FSM (READY/PAUSED/FAILED/STOPPING) поверх `LifecycleState`.

**Smoke.**
```
python bootstrap.py → Kernel started → Registry/Bus/Scheduler запущены
Runtime Loop тикает (kernel.running == True), НЕТ вызова agent.ask()
```

---

## Уровень 2 — Platform Integration

**Goal.** Полностью интегрировать существующие платформы как процессы.

**Компоненты:**
```
Kernel
├── AgentPlatform        (библиотека → Process через IServiceLifecycle)
├── KnowledgePlatform    (библиотека → Process)
├── MemoryPlatform       (библиотека → Process)
├── WorkflowPlatform     (build_executor → Process)
├── LearningPlatform     (InMemoryLearningStore → Process)
├── OptimizationPlatform (PatternBasedOptimizer → Process)
├── API Platform         (KROFT_OSServer, legacy → Process)
├── Desktop Platform     (DesktopService, legacy → Process)
└── MCP Platform         (PLANNED — не существует в коде)
```
(дерево из вашего запроса)

**Guardrails (сохранить).**
- `Kernel` НЕ знает `LLM/Knowledge/Memory/Desktop/API/MCP` — только `IServiceLifecycle` + `IProcess`.
- Интеграция платформ идёт ЧЕРЕЗ `ProcessRegistry`, не через прямые импорты в `kernel.py`.
- `MCP Platform` — PLANNED; появится только когда `ProcessRegistry` (Level 1) готов и расширен.

**Definition of Done.**
- Все 8 платформ (7 существующих + MCP future) зарегистрированы в `ProcessRegistry`
  и управляются ядром как процессы (не библиотеки).
- `Kernel` не содержит ни одного `from services.X import Y` для платформ.

**Smoke.**
```
запустить Kernel → 8 процессов (Agent/Memory/Knowledge/Workflow/Learning/
Optimization/API/Desktop) зарегистрированы; ядро не импортирует платформы
```

---

## У句话说 3 — Runtime Services

**Goal.** Сервисы САМОГО ядра (не платформы).

**Компоненты:**
```
Metrics Service      (metrics() в Kernel)
Logging Service      (logger в RuntimeContext)
Tracing Service      (trace в EventBus.publish)
Configuration Service (runtime_config.py)
Secrets Service      (если появится — НЕ в ядре напрямую)
Cache Service        (infra Cache — третий тип)
Snapshot Service     (SnapshotStore уже в Kernel)
Recovery Service     (Stage 19 restore)
Checkpoint Service   (SnapshotStore.save)
```

**Guardrails.**
- Это НЕ платформы волн 11–14 (те — библиотеки домена, не инфраструктура ядра).
- Runtime Services живут ВНУТРИ ядра (`kernel`/`runtime` пакеты), не в `services/`.

**Definition of Done.**
- `Kernel.metrics()` / `Logging` / `Tracing` / `Config` / `Snapshot` / `Recovery` /
  `Checkpoint` реализованы и вызываются из ядра (не из платформ).
- Service Classification (Kernel Review §3) соблюдена: Infrastructure ≠ Library.

**Sm唐诗oke.**
```
start() → metrics ticks; logger пишет; snapshot сохраняется при stop()
```

---

## Уровень 4 — Resource Manager

**Goal.** Квоты: каждый процесс получает лимиты.

**Компоненты:** `CPU Budget` / `Memory Budget` / `GPU Budget` / `Token Budget` /
`Context Budget` / `IO Budget`.

**Guardrails.**
- Бюджеты НЕ мутируют состояние платформ (те — библиотеки, не процессы).
- Resource Manager — инфраструктура ядра, НЕ доменная платформа.

**Definition of Done.**
- `KnowledgePlatform` задocumented с лимитами (RAM 512MB / GPU 0 / CPU 20%) через
  `ProcessRegistry` (не через платформенный код).
- Ядро эластично к нехватке ресурса (не падает, если budget=0).

**Smoke.**
```
процесс стартует с лимитом; превышение бюджета → Supervisor (Level G) throttle/restart
```

---

## Уровень 5 — Scheduler 2.0

**Goal.** Мини-K8s scheduler внутри KROFT_OS.

**Компоненты:** `Priority / Deadline / Dependency / Retry / Timeout / Cancellation /
Backpressure / Fair Scheduling` (расширение существующего `SchedulerService`).

**Guardrails.**
- Scheduler остаётся ЧАСТЬЮ Runtime Loop (Phase E), не отдельным сервисом вне ядра.
- Не лезет в LLM/desktop/api логику платформ.

**Definition of Done.**
- `Scheduler.tick()` в цикле умеет priority/deadline/dependency/retry/timeout/cancel/
  backpressure/fair (расширяет `services/scheduler.py`, НЕ переписывает его).
- Kernel Review cycle-аудит: Scheduler по-прежнему принадлежит ядру.

**Smoke.**
```
loop тикает: scheduler выбирает priority-задачу, соблюдает deadline/retry/timeout
```

---

## Уровень 6 — IPC

**Goal.** Два механизма: Event (`publish/subscribe`) + Request (`call/reply`).

**Компоненты:** `EventBus.publish/subscribe` (уже есть) + `Request.call/reply` (новый
примитив в `IEventBus` или отдельном `IRequestBus`).

**Guardrails.**
- Request/Reply НЕ заменяет EventBus (шина — собственность Kernel, не платформ).
- Процессы не знают друг о друге (только через IPC-примитивы ядра).

**Definition of Done.**
- Ядро предоставляет `call/reply` наравне с `publish/subscribe`.
- Платформы общаются через IPC, НЕ импортируя друг друга напрямую.

**Smoke.**
```
процесс A делает request → ядро router → процесс B отвечает reply; без прямого импорта B в A
```

---

## Уровень 7 — Capability System

**Goal.** Не `AgentPlatform`, а `Capability` (Search/Summarize/Translate/Reason/Code/Vision).

**Компоненты:** `CapabilityRegistry` (уже есть `runtime/CapabilityRegistry`!) → выдаёт
процессу capability, НЕ наоборот.

**Guardrails.**
- `Kernel` выдаёт capability процессу через `ICapabilityRegistry` (уже резолвится в
  `kernel.kernel.Kernel`), НЕ платформа выдаёт ядру.
- Capability — НЕ доменная платформа (Search/Summarize/… — это возможности, не AgentPlatform).

**Definition of Done.**
- `CapabilityRegistry` (runtime/) интегрирован в ядро; процессы получают capability
  от ядра, не от платформ.
- Проверка арх-аудита: capability — часть инфраструктуры, НЕ библиотеки домена.

**Smoke.**
```
процесс резолвит capability через kernel (ICapabilityRegistry), НЕ импортируя платформу
```

---

## Уровень 8 — Plugin Runtime

**Goal.** Настоящий Marketplace.

**Компоненты:** `Plugin → Manifest → Capability → Sandbox → Lifecycle → Registry`.

**Guardrails.**
- Plugin НЕ мутирует состояние ядра (kernel остаётся тем же FSM).
- Manifest/Capability/Sandbox/Lifecycle — инфраструктура, НЕ доменные платформы.

**Definition of Done.**
- Plugin регистрируется в `ProcessRegistry` (как процесс, не библиотека).
- Marketplace работает БЕЗ изменения `Kernel` (дополняет, не дублирует).

**Smoke.**
```
загрузить plugin (manifest) → capability выдана → sandbox запущен → lifecycle зарегистрирован
```

---

## Уровень 9 — Security

**Goal.** Изоляция и расширяемость.

**Компоненты:** `Permissions / Capability Tokens / Secrets / Policy / Sandbox / Audit`.

**Guardrails.**
- Security — инфраструктура ядра, НЕ доменная платформа (не лезет в логику AgentPlatform).
- Capability Token выдаётся ядром, НЕ платформой.

**Definition of Done.**
- Ядро энфорсит permissions/capability-tokens/secrets/policy/sandbox/audit.
- Платформы получают доступ через capability, НЕ к объектам ядра напрямую.

**Smoke.**
```
процесс запрашивает permission через capability-token → audit логирует решение ядра
```

---

## Уровень 10 — Distributed Kernel

**Goal.** Desktop ↓ Server ↓ Cluster ↓ Remote Runtime. Process Registry становится распределённым.

**Компоненты:** `Remote Registry` / `Remote Runtime` (расширение `ProcessRegistry`).

**Guardrails.**
- Локальный FSM и контракты НЕ меняются для distributed (ядро те же методы).
- Транспорт между узлами — за интерфейсом (adapter), ядро не знает сети напрямую.

**Definition of Done.**
- Remote Registry зеркалит локальный; cross-node процесс виден в объединённом реестре.
- Запуск процесса на удалённом узле через тот же `ProcessRegistry` API.

**Smoke.**
```
зарегистрировать remote node → процесс виден в merged registry
команда start на remote → процесс RUNNING на удалённом узле
```

---

## Уровень 11 — Autonomous Kernel

**Goal.** Автономность — СВОЙСТВО ядра, не отдельной платформы.

**Компоненты:** self-detect / restart / rebalance / optimize routing / self-heal (без
изменения доменных платформ 11–14).

**Guardrails.**
- Автономность достигается расширением `Kernel`, НЕ добавлением новой платформы.
- Не дублировать `kernel/kernel.py` (уже реализован).

**Definition of Done.**
- `Kernel` сам обнаруживает проблемы / перезапускает процессы / балансирует ресурсы
  / оптимизирует маршрутизацию моделей / меняет конфиг по политике / делает safe self-heal.
- Платформы 11–14 остаются библиотеками (не получают автономность сами).

**Smoke.**
```
kernel в RUNNING сам перезапускает упавший процесс (Supervisor Level G); routing оптимизируется
```

---

## Уровень 12 — Production ES

**Goal.** Качество, не новые функции.

**Компоненты:** `Chaos Engineering / Fault Injection / Soak Tests (72–168h) / Leak Detection /
Deadlock Detection / Perf Regression / Recovery Drills / Version Compat / Migration Tests`.

**Guardrails.**
- Тесты не разрушают prod-данные (изолированный стенд).
- Fault Injection — за флагом, не в обычном прогоне.

**Definition of Done.**
- Все suite (chaos/fault/soak/leak/deadlock/perf/recovery/version/migration) зелёные.
- Long-running прогон стабилен (нет утечек/дедлоков за 72h+).

**Smoke.**
```
прогнать chaos (убийство случайного процесса) → Supervisor восстанавливает; состояние консистентно
```

---

## Недостающие архитектурные эпики (ваши 3)

### Эпик R — Runtime Resource Management

**Goal.** Квоты и управление ресурсами (Level 4 уже опирается). Без него нельзя
масштабировать и запускать несколько агентов одновременно.

**Components:** `CPU Budget / Memory Budget / GPU Budget / Token Budget / Context Budget / IO Budget`.
**Guardrails.** Не мутирует состояние платформ (те — библиотеки). Resource Manager —
инфраструктура ядра, НЕ доменная платформа.
**DoD.** Ядро эластично к нехватке ресурса; процессы получают лимиты через `ProcessRegistry`.
**Smoke.** процесс стартует с лимитом; превышение → throttle/restart (Supervisor).

### Эпик I — IPC / Service Communication

**Goal.** Разделить Event (publish/subscribe) и синхронный Request-Reply (RPC). Избавляет
платформы от прямых зависимостей друг к другу.

**Components:** `EventBus.publish/subscribe` (есть) + `Request.call/reply` (новый примитив).
**Guardrails.** Request/Reply не заменяет EventBus (шина — собственность Kernel). Процессы
не знают друг о друге напрямую.
**DoD.** Ядро предоставляет оба механизма; платформы общаются через IPC, не импортируя друг друга.
**Smoke.** процесс A делает request → ядро router → процесс B отвечает reply.

### Эпик C — Capability & Permission Framework

**Goal.** Расширяемость + безопасность. Новые плагины/платформы получают доступ к
строго определённым **capabilities**, не к объектам ядра.

**Components:** `CapabilityRegistry` (runtime/) + `Permission/Capability-Token/Sandbox`.
**Guardrails.** Capability — инфраструктура, НЕ библиотека домена. Ядро выдаёт capability,
не платформа.
**DoD.** Платформы получают доступ через capability (изоляция + Marketplace-готовность).
**Smoke.** процесс резолвит capability через `ICapabilityRegistry`, НЕ импортируя платформу.

---

## Discipline (ритм «реализация → аудит → итерация»)

После КАЖДОГО крупного уровня (1–12) и каждого эпика (R/I/C):
1. Прогнать пакетный DAG-аудит (подтверждено в Kernel Review: циклов НЕТ).
2. Проверить, что `Kernel` НЕ импортирует платформы волн 11–14 (только contracts).
3. Подтвердить, что `ProcessRegistry` (а не `DependencyContainer`) владеет состоянием процессов.
4. Убедиться, что шина принадлежит `Kernel`, не `AgentPlatform`.

Если любой пункт нарушен — уровень НЕ закрыт (арх-аудит провален), даже если код написан.

---

## Связь с предыдущими ADR

- **ADR-018** (Phase A, `in_progress`) → Level 1 bootstraps ядро.
- **ADR-019** (контракт ядра) → Levels 1–3 опираются на него; 4–12 его расширяют.
- **Kernel Review (Phase 0.5)** → заземлил факты (Kernel существует, платформы — библиотеки, DAG без циклов).
- **Bootstrap Initiative v2 Master Roadmap** → Level 1 = Phase B (Kernel Runtime API), Level 2 = Platform Integration, Level 3 = Runtime Services.
- **Этот документ** → 12 Levels + 3 эпика, с DoD/Guardrails/Smoke на каждый.
