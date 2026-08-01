---
tags: [kroft, kernel, review, architecture, bootstrap]
created: 2026-07-31
status: review
version: 1.0
author: Hermes (senior software architect)
depends_on: [ADR-018, ADR-019, Bootstrap Initiative v2 — Master Roadmap]
summary: >-
  Kernel Review (Phase 0.5) — обязательная архитектурная ревизия перед заморозкой
  ядра. Process Inventory, Dependency Audit (циклы: НЕТ), Service Classification,
  Ownership Matrix, Startup/Shutdown, Failure Matrix, State Machine Audit. Ключевое
  открытие: Kernel УЖЕ реализован (kernel/kernel.py) — Phase B должна дополнять,
  не дублировать.
---

# Kernel Review (Phase 0.5) — финальная архитектурная ревизия

> Статус: **review** (2026-07-31). Read-only аудит системы относительно будущего
> Runtime. Без кода. Все выводы заземлены в реальные файлы (grep + AST-граф
> импортов), не по описанию.
>
> **Главное открытие (спасшее от параллельного мира):** в репо УЖЕ есть
> `kernel/kernel.py` с рабочим классом `Kernel` (FSM `LifecycleState`,
> `initialize/start/stop/save/emit`, владеет `DependencyContainer`+`IEventBus`+
> `SnapshotStore`). Значит Phase B НЕ должна создавать `runtime/kernel_runtime.py`
> с нуля — она должна **дополнить существующий `Kernel`** до контракта ADR-019.
> Иначе мы повторили бы ошибку `main.py` (параллельный мир рядом с платформами).

## 1. Process Inventory

Полная карта существующих платформ/сервисов (реальные классы из `services/`+`adapters/`).

| Компонент | Тип (реально) | Владелец | Запускает | Останавливает | Permanent? | Restart? | Зависит от | Process or Library? |
|---|---|---|---|---|---|---|---|---|
| `Kernel` (`kernel/kernel.py`) | ядро | OS | `Kernel.start()` | `Kernel.stop()` | да | restart=self | container, IEventBus, IFileSystem, IGraphBuilder | **Process** (ядро) |
| `AgentPlatform` | оркестратор | composition root | — (нет start) | — | нет метода | через re-create | planner, executor, router, memory, knowledge, learning, optimizer, autonomy | **Library** |
| `MemoryPlatform` | сервис | composition root | — | — | нет | re-create | `IMemoryStore` | **Library** |
| `KnowledgePlatform` | сервис | composition root | — | — | нет | re-create | `IKnowledgeGraph`, `IEntityExtractor` | **Library** |
| `WorkflowPlatform` (через `build_executor`) | оркестратор | composition root | — | — | нет | re-create | IPlanner, IExecutor(Reflection/Retry) | **Library** |
| `LearningPlatform` (`InMemoryLearningStore`) | store | composition root | — | — | нет | re-create | `IMemoryStore` | **Library** |
| `OptimizationPlatform` (`PatternBasedOptimizer`) | предложение | composition root | — | — | нет | re-create | `ILearningStore` (patterns) | **Library** |
| `DesktopPlatform` (`DesktopService`, legacy) | сервис | `main.py` | — | — | нет | re-create | `IDesktop` | **Library** (legacy) |
| `APIPlatform` (`KROFT_OSServer`, legacy) | сервер | `main.py` | `start()` | — | да (daemon) | re-start | container | **Process** (legacy) |
| `SchedulerService` | планировщик | `main.py` / Kernel | `start()` (daemon thread) | `stop()` | да | restart | `IFileSystem`, executor | **Process** |
| `EventBus` (`InMemoryEventBus`) | шина | Kernel (владеет) | `start()` | `stop()` | да | re-create | — | **Infrastructure** |
| `DependencyContainer` | локатор | composition root | — | — | да | re-create | — | **Infrastructure** |
| `Router` (`adapters/router.py`) | роутер | composition root | — | — | нет | re-create | PolicyEngine, adapters map | **Library** |
| `VaultStreamCrawler` (legacy `IService`) | crawler | `main.py` | `initialize/execute` | — | нет | re-create | IFileSystem, IEventBus, IGraphBuilder | **Process** (legacy IService) |
| `WatchService` (legacy `IService`) | watcher | `main.py` | `initialize/execute` | — | нет | re-create | crawler, watcher | **Process** (legacy) |
| `GraphQueryEngine` (orphaned) | query | `main.py` | `start()` | — | да | re-create | graph, index | **Process** (orphaned) |
| `MockLlmAdapter`/`OmniRouteAdapter` | LLM | Router | — | — | нет | swap | — | **Library/Adapter** |

**Вывод:** платформы волн 11–14 (`AgentPlatform`/`MemoryPlatform`/`KnowledgePlatform`/
`WorkflowPlatform`/`LearningPlatform`/`OptimizationPlatform`) НЕ имеют НИ ОДНОГО
lifecycle-метода (`start/stop/initialize/pause/resume`) — подтверждено grep'ом.
Они — **библиотеки/оркестраторы**, не процессы. Чтобы стать процессами ядра,
нужен адаптер `IServiceLifecycle` (Phase C), который завернёт их без изменения
самих платформ.

## 2. Dependency Audit (реальный AST-граф)

Построен граф импортов по пакетам (ADR-019 cycle-detection script). Рёбра
(схлопнуто):

```
adapters   -> contracts
infrastructure -> contracts
runtime     -> contracts
services    -> contracts
kernel      -> contracts, infrastructure, runtime
cli         -> infrastructure, kernel, services
```

**Циклы: НЕТ.** Граф — DAG. `contracts` — лист (никто не импортирует обратно).
Иерарция строгая: contracts ← {adapters, infrastructure, runtime, services} ←
kernel ← cli. Никаких cross-layer циклов. `services↔services` через `importlib`
в `workflow_runner.py` — ленивый, защищённый, НЕ статический цикл.

**Отмеченный риск (не цикл, но дубликат):** `kernel/kernel.py` УЖЕ реализует ядро.
Если Phase B создаст `runtime/kernel_runtime.py` как новый `KernelRuntime` —
получится **второе ядро** рядом с существующим. Это тот же класс ошибки, что
`main.py` vs платформы 11–14. **Решение (см. §8):** Phase B расширяет `Kernel`,
не дублирует.

## 3. Service Classification

Три типа (ваш пункт 3), grounded:

**Processes (живут постоянно, регистрируются в ProcessRegistry):**
- `Kernel` (ядро)
- `SchedulerService` (daemon thread, `start/stop`)
- `APIPlatform` (`KROFT_OSServer`, `start()`)
- `VaultStreamCrawler` / `WatchService` (legacy `IService`, `initialize/execute`)
- `GraphQueryEngine` (orphaned, `start()`)
- `EventBus` (самостоятельный процесс шины)
- `Supervisor/Watchdog` (Phase G, будущий)

**Libraries (не живут, НЕЛЬЗЯ регистрировать как процессы):**
- `AgentPlatform`, `MemoryPlatform`, `KnowledgePlatform`, `WorkflowPlatform`,
  `LearningPlatform`, `OptimizationPlatform` (оркестраторы/store — нет lifecycle)
- `EmbeddingService`/`MockEmbeddingAdapter`, `VectorSearch`, `Parser`,
  `RuleBasedPlanner`, `PatternBasedOptimizer`, `Router`, `LLM-адаптеры`
- Их нельзя пихать в ProcessRegistry как процессы; они — зависимости процессов
  (инъекция через container).

**Infrastructure (третий тип, не процессы и не библиотеки домена):**
- `DependencyContainer` (локатор)
- `RuntimeContext` / `CapabilityRegistry` (runtime/)
- `SnapshotStore` (persistence)
- `Config` / `Logger` / `Metrics` / `Cache` (Phase I/J придут — пока в зачатках)

## 4. Ownership Matrix

Кто чем владеет (проверено в `kernel/kernel.py`):

```
Kernel
  ├── owns: DependencyContainer (self.container)
  ├── owns: IEventBus        (self._event_bus, вызывает start/stop)
  ├── owns: SnapshotStore    (self._snapshot_store)
  ├── owns: RuntimeContext   (self.runtime_context)
  └── resolves (container): ICapabilityRegistry, IFileSystem, IGraphBuilder
        └── НЕ владеет ими — только ссылки
```

**Критически важно (ваш пример):** `EventBus` владеет **Kernel**, НЕ
`AgentPlatform`. В `kernel.py` именно `Kernel.emit()` → `self._event_bus.publish_sync()`.
`AgentPlatform` шину НЕ создаёт и не владеет ей. Это правильно — подтверждает
контракт ADR-019 («Kernel владеет EventBus»).

Платформы (Agent/Memory/Knowledge/...) — НЕ владеют шиной, НЕ владеют ядром.
Они резолвятся Kernel'ом из container и вызываются как библиотеки.

## 5. Startup Sequence (реальная, из kernel.py + bootstrap.py)

```
Config / bootstrap args
    ↓
DependencyContainer (регистрация adapters/платформ)
    ↓
Kernel(container)                    # __init__: UNINITIALIZED
    ↓
Kernel.initialize()                  # INITIALIZED; резолв cap, IEventBus.start(), restore graph/index
    ↓
Kernel.start()                       # RUNNING; для каждого svc в container: svc.initialize(); emit kernel.started
    ↓
    (legacy main.py: cmd_* резолвит из container)
    (bootstrap.py Phase A: agent.ask() один раз — НЕ цикл)
Будущий Runtime Loop (Phase E):
    ↓
while kernel.running: bus.poll(); scheduler.tick(); registry.monitor(); supervisor.watch(); metrics.flush()
```

Платформы волн 11–14 сейчас НЕ стартуются через `Kernel.start()` (Kernel резолвит
только `ICapabilityRegistry/IFileSystem/IEventBus/IGraphBuilder`). Это gap:
AgentPlatform и др. надо зарегистрировать в container и дать им lifecycle-адаптер
(Phase C/D), чтобы Kernel мог их `initialize()` при старте.

## 6. Shutdown Sequence (реальная, из kernel.py)

```
Kernel.stop()                        # STOPPING-логика (idempotent)
    ↓
_stop_autosave()                     # сначала отменить watchdog
    ↓
_try_snapshot_graph()                # сохранить граф + индекс
    ↓
emit kernel.stopped
    ↓
_services.clear()
    ↓
IEventBus.stop()
    ↓
STOPPED
```

Уже реализовано корректно: idempotent (повторный `stop()` — no-op), snapshot
перед очисткой, шина останавливается последней. **Чего нет:** перехвата
`SIGINT`/`SIGTERM`/Windows Console Ctrl-C (Phase F) и `dispose()` сервисов
(сейчас только `clear()`, не `dispose()`).

## 7. Failure Matrix (проекция на будущий Supervisor)

| Сбой | Текущее поведение | Назначение (Phase G) |
|---|---|---|
| `SchedulerService` crashed | daemon thread умирает; ядро не знает | `Supervisor.restart()` (backoff) |
| `KnowledgePlatform` crashed | не процесс (library) — исключение проваливается в вызывающего | `disable` + `continue` (изолировать) |
| `AgentPlatform` crashed | исключение → `WorkflowStatus.FAILED` (перехвачено в `run()`) | `panic` при каскаде; `restart` одиночного |
| `EventBus` down | `emit` no-op (Kernel эластичен) | `Kernel` переходит в `STOPPING` (шина — критична) |
| `GraphQueryEngine` (orphaned) crashed | независимый процесс | `disable` (не блокирует ядро) |

`Kernel` уже эластичен к отсутствию шины (`emit` no-op при `None`). Это хорошая
база для Failure Matrix.

## 8. State Machine Audit

**Конфликтующие состояния: есть.** Два разных FSM в коде:

- `kernel/LifecycleState`: `UNINITIALIZED → INITIALIZED → RUNNING → STOPPED`
  (4 состояния, НЕТ PAUSED/FAILED).
- Ваш ADR-019 / Master Roadmap требует: `INITIALIZING → READY → RUNNING →
  PAUSED → STOPPING → STOPPED → FAILED` (единый для Kernel/Platform/Process).

**Решение (до Phase B):** унифицировать. `Kernel.LifecycleState` расширяется до
единого FSM из ADR-019: добавить `PAUSED` (Kernel пока не умеет pause/resume),
`FAILED`, `READY` (между INITIALIZED и RUNNING), `STOPPING`. И `IServiceLifecycle`
сервисов (Phase C) использует ТОТ ЖЕ набор состояний (сервисный FSM:
`CREATED→INITIALIZED→STARTING→READY→RUNNING→PAUSED→STOPPING→STOPPED→FAILED→DISPOSED`).
Без этого — расхождение терминов, которое сломает ProcessRegistry (Phase D),
где статус процесса должен быть из единого словаря.

**Ещё один конфликт:** `WorkflowStatus` (DONE/FAILED/PENDING) и `AgentStatus`
(DONE/FAILED/PARTIAL) — это состояния *задачи*, не ядра; они вне FSM ядра, НЕ
конфликтуют, но ProcessRegistry должен их не путать с `RuntimeState`.

## 9. Итоговая дорожная карта (ваша, подтверждена + уточнена)

```
Kernel Review (этот документ)        ← сделан
    │  открытие: Kernel УЖЕ есть → Phase B дополняет, не дублирует
    ▼
ADR-019 (готов, draft)
    ▼
Process Inventory (§1) + Dependency Audit (§2: циклов НЕТ)
    ▼
Ownership Matrix (§4) + Service Classification (§3)
    ▼
Startup / Shutdown (§5/§6) + Failure Matrix (§7)
    ▼
State Machine Audit (§8: унифицировать FSM до Phase B)
    ▼
Phase B — Kernel Runtime API
    └─ НЕ создавать runtime/kernel_runtime.py; РАСШИРИТЬ kernel/kernel.py:
       + pause()/resume()/restart()/health()/services()/metrics()
       + единый RuntimeState FSM (READY/PAUSED/FAILED/STOPPING)
    ▼
Phase B.5 — Runtime Verification (архитектурные тесты: Registry/Bus/Scheduler/
         StateMachine существуют и соответствуют ADR-019)
    ▼
Phase C — Lifecycle Manager (IServiceLifecycle для платформ-библиотек)
    ▼
Phase D — Process Registry (поверх container, владеет состоянием)
    ▼
Phase E — Runtime Event Loop (IEventBus.poll + Scheduler в цикле)
    ▼
Phase F — Graceful Shutdown (SIGINT/SIGTERM/Windows + dispose)
    ▼
... (G–L как в Master Roadmap)
```

## 10. Честные выводы (что сломать/доделать ДО Phase B)

1. **Не создавать второе ядро.** Phase B дополняет `kernel/kernel.py`, не пишет
   `runtime/kernel_runtime.py`. (Спасено от параллельного мира.)
2. **Унифицировать FSM** (§8) до Phase B — иначе ProcessRegistry получит
   расходящиеся состояния.
3. **Платформы 11–14 — библиотеки** (§1/§3). Phase C даёт им `IServiceLifecycle`-
   адаптер; Phase D регистрирует как процессы. Не путать с Infrastructure.
4. **EventBus уже принадлежит Kernel** (§4) — контракт ADR-019 подтверждён кодом.
5. **Shutdown частично готов** (§6): есть idempotent stop+snapshot, НЕТ сигналов
   и dispose (Phase F).
6. **Dependency cycles: отсутствуют** (§2) — ломать нечего; иерархия чистая.

---
*Ревизия завершена. Система готова к Phase B при условии дополнения существующего
`Kernel`, а не создания дубликата. Никакой код в этом документе не пишется.*
