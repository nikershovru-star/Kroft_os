---
tags: [kroft, adr, kernel, runtime, architecture, epic]
created: 2026-07-31
status: draft
version: 1.0
author: Hermes (senior software architect)
depends_on: [ADR-018]
summary: >-
  Bootstrap Initiative — Этап 1 (Kernel Architecture, без реализации). Контракт
  ядра KROFT_OS: что такое Kernel, чем Runtime отличается от Bootstrap, кто
  владеет жизненным циклом/процессами/состоянием/EventBus, где Scheduler/
  Watchdog/HealthMonitor. Фундамент для Phase B (Runtime Skeleton).
---

# ADR-019 — Kernel Runtime Architecture

> Статус: **draft** (2026-07-31). Утверждается пользователем ДО начала Этапа 2
> (Runtime Skeleton). Это Этап 1 инициативы **Bootstrap Initiative** — документ
> описывает *контракт ядра*, не код. После утверждения нельзя спорить о
> направлении; можно спорить только о наполнении.

## 0. Мотивация (почему ADR-019, а не код сразу)

`bootstrap.py` (ADR-018, Phase A) собирает DI-контейнер и вызывает `agent.ask()`
один раз, затем завершается:

```
bootstrap.py → build container → agent.ask() → exit
```

Это **CLI-приложение**, не операционная система. Настоящая ОС — это непрерывный
жизненный цикл:

```
Boot → Runtime → Scheduler → Event Bus → Agent Loop → Shutdown
```

Писать Runtime до фиксации контракта ядра опасно: пришлось бы переделывать
почти все платформы. Поэтому сначала — этот документ (контракт), затем
Этап 2 (скелет API), затем поэтапное наполнение сверху вниз.

## 1. Что такое Kernel

**Kernel** — это объект `KernelRuntime`, единственный владелец непрерывного
жизненного цикла ОС. Он:

- владеет **EventBus** (шина — собственность ядра, а не bootstrap и не платформ);
- владеет **ProcessRegistry** (каталог всех процессов/платформ и их состояний);
- создаёт и завершает **процессы** (платформы как процессы, не как сервисы);
- отвечает за **состояние ОС** (`kernel.state()`);
- управляет **жизненным циклом** всех платформ через Lifecycle Manager;
- крутит **Runtime Event Loop** (`while kernel.running: bus.poll(); scheduler.tick(); ...`);
- обеспечивает **graceful shutdown** и (позже) **hot reload**.

Kernel ≠ набор платформ. Kernel = оркестратор, который держит платформы живыми
и связными через шину.

## 2. Runtime отличается от Bootstrap (ключевое различие)

| | Bootstrap (Phase A, готово) | Runtime (Phase B+, этот АДР) |
|---|---|---|
| Назначение | Собрать DI-контейнер, поднять адаптеры | Держать ОС живой в цикле |
| Жизнь | Однократный вызов, затем `exit` | Непрерывный `while running` |
| Владение шиной | Нет (шина — инстанс в контейнере) | Да (Kernel владеет EventBus) |
| Управление процессами | Нет (платформы — инстансы) | Да (Lifecycle + ProcessRegistry) |
| Состояние ОС | Нет | `kernel.state()` / `kernel.health()` |
| Цикл | `agent.ask()` один раз | Agent Loop + Scheduler + Bus poll |

**Вывод:** Bootstrap — это *точка входа*, которая передаёт управление Runtime.
Bootstrap не является Runtime. Runtime не существует до Phase B.

## 3. Распределение ответственности (явные ответы)

- **Кто владеет жизненным циклом платформ?** → `KernelRuntime` через
  `LifecycleManager` (Phase C). Платформа сама не управляет своим циклом; ядро
  вызывает `initialize → start → ready → stop → dispose`.
- **Кто создаёт процессы?** → `KernelRuntime` (+ `ProcessRegistry`), по контракту
  `IServiceLifecycle`.
- **Кто завершает процессы?** → `KernelRuntime` (graceful shutdown, Phase F),
  принудительно — `Supervisor/Watchdog` (Phase G) при зависании.
- **Кто отвечает за состояние ОС?** → `KernelRuntime.state()` возвращает
  агрегат состояний всех процессов из `ProcessRegistry`.
- **Кто владеет EventBus?** → `KernelRuntime`. Шина создаётся ядром, платформы
  только `subscribe`/`publish`. Bootstrap НЕ владеет шиной.
- **Где Scheduler?** → Зарегистрирован в `ProcessRegistry` как процесс
  `scheduler` (уже реализован: `services/scheduler.py::SchedulerService`,
  daemon-thread, JSON-persistence). Ядро вызывает `scheduler.tick()` в цикле.
- **Где Watchdog / HealthMonitor?** → Под `KernelRuntime` (Phase G Supervisor).
  `health()` агрегирует метрики; Watchdog перезапускает зависшие процессы.

## 4. Контракты ядра (сигнатуры, без реализации)

### 4.1 KernelRuntime (фундамент, Phase B)

```
KernelRuntime
├── start()              # Boot → Runtime: инициализировать шины, процессы, цикл
├── stop()               # Graceful shutdown (Phase F)
├── restart()            # stop() + start() атомарно
├── pause()              # заморозить цикл, процессы живы но не тикают
├── resume()             # продолжить цикл
├── state() -> KernelState   # агрегат состояний всех процессов
├── health() -> HealthReport  # метрики + статусы (для Watchdog)
├── services() -> List[ProcessHandle]  # снимок ProcessRegistry
└── bus: IEventBus       # собственность ядра
```

### 4.2 IServiceLifecycle (расширение существующего IService, Phase C)

Существующий `contracts/i_service.py::IService` имеет только `name/initialize/
execute`. Добавляется контракт жизненного цикла (ваш список):

```
IServiceLifecycle(IService):
    initialize(context)   # уже есть
    start()                # начать работу процесса
    ready() -> bool        # процесс готов принимать события
    stop()                 # корректно остановить
    dispose()              # освободить ресурсы
```

Платформы (AgentPlatform, MemoryPlatform, KnowledgePlatform, WorkflowPlatform,
DesktopPlatform, APIPlatform, MCPGateway) должны реализовать `IServiceLifecycle`,
чтобы стать **процессами**, а не сервисами.

### 4.3 IProcessRegistry (Phase D)

```
IProcessRegistry:
    register(handle: ProcessHandle)
    unregister(pid: str)
    get(pid: str) -> ProcessHandle
    list() -> List[ProcessHandle]
    state(pid: str) -> ProcessState
```

`DependencyContainer` (infrastructure) хранит инстансы, но НЕ управляет
жизненным циклом — поэтому он не является ProcessRegistry. ProcessRegistry
строится ПОВЕРХ container и добавляет владение состоянием/жизненным циклом.

### 4.4 IEventBus.poll (добавление в contracts/i_event_bus.py, Phase E)

Текущий `IEventBus` — push-only (`subscribe/publish/publish_sync`). Event Loop
требует вытягивания:

```
IEventBus:
    poll(timeout: float) -> Optional[Event]   # НОВОЕ
    # существующие: subscribe / publish / publish_sync / get_history / start / stop
```

Без `poll()` непрерывный цикл `while running: bus.poll()` невозможен.

### 4.5 IWatchdog / IHealthMonitor (Phase G)

```
IWatchdog:
    watch(pid: str, timeout: float)
    on_stall(pid: str) -> restart | alert
IHealthMonitor:
    probe(pid: str) -> HealthStatus
```

## 5. Дерево процессов (Process Registry — grounded)

```
Kernel
├── agent_platform      (EXISTS: services/agent_platform.py, Wave 11)
├── workflow_platform   (EXISTS: services/workflow_runner.build_executor, Wave 10)
├── memory_platform     (EXISTS: services/memory_platform.py, Wave 9)
├── knowledge_platform  (EXISTS: services/knowledge_platform.py, Wave 8)
├── learning_platform   (EXISTS: adapters/in_memory_learning_store.py, Wave 12)
├── optimization_platform (EXISTS: services/pattern_based_optimizer.py, Wave 13)
├── desktop_platform    (LEGACY: services/desktop_service.py — мигрирует в процесс)
├── api_platform        (LEGACY: adapters/http_server.KROFT_OSServer — мигрирует)
├── scheduler           (EXISTS: services/scheduler.py::SchedulerService)
├── event_bus           (EXISTS: infrastructure/eventbus.py::InMemoryEventBus)
├── mcp_gateway         (PLANNED: не существует в коде)
└── supervisor/watchdog (PLANNED: Phase G)
```

Пометки: **EXISTS** = реализован как инстанс/сервис; **LEGACY** = работает в
`main.py`, но не как процесс ядра (миграция по модулю, как в ADR-018 S4);
**PLANNED** = отсутствует, появится в соответствующей фазе.

## 6. Эпик Bootstrap Initiative (Phase A–H, сверху вниз)

```
Bootstrap Initiative
A  Composition Root        ✅ ГОТОВО (ADR-018: bootstrap.py)
B  Kernel Runtime API       ⬜ Этап 2: KernelRuntime skeleton (пустые методы)
C  Lifecycle Manager        ⬜ IServiceLifecycle + управление циклом
D  Process Registry         ⬜ IProcessRegistry поверх container
E  Runtime Event Loop       ⬜ while running: bus.poll(); scheduler.tick(); ...
F  Graceful Shutdown        ⬜ stop() с корректным завершением процессов
G  Supervisor / Watchdog    ⬜ IWatchdog + IHealthMonitor + перезапуск
H  Hot Reload               ⬜ замена процесса без остановки ядра
```

**Важно:** `Runtime API` (Phase B) выделен отдельно и идёт ПЕРЕД наполнением.
Это фундамент: сначала фиксируем `KernelRuntime.*`, потом наполняем жизнью.

## 7. Границы (что НЕ делается в Этапе 1)

- Этап 1 — **только этот документ**. Никакого кода.
- Не расширять `IService`/`IEventBus` до утверждения ADR-019.
- Не писать `KernelRuntime` до Этапа 2.
- Не трогать `bootstrap.py` (он остаётся Phase A entrypoint, который позже
  передаст управление `KernelRuntime`).

## 8. Честные gaps (что должно появиться в фазах B–E)

1. `IEventBus.poll()` отсутствует → Event Loop невозможен (Phase E).
2. `IServiceLifecycle` (`start/ready/stop/dispose`) отсутствует → платформы не
   процессы (Phase C).
3. `KernelRuntime` не существует (Phase B).
4. `ProcessRegistry` не существует (container ≠ registry) (Phase D).
5. `SchedulerService` уже готов — вписывается как процесс, не пишется заново.
6. `Watchdog`/`HealthMonitor`/`MCPGateway` отсутствуют (Phase G / PLANNED).

## 9. Следующий шаг (после утверждения)

Этап 2 — **Runtime Skeleton**: создать `kernel_runtime.py` с классом
`KernelRuntime`, реализующим ВСЕ методы из §4.1, но **почти пустыми**
(`start()` регистрирует шину и процессы, `state()` возвращает `booting`,
цикл ещё не крутится). Главная цель Этапа 2 — **закрепить API ядра**, не
поведение. Наполнение (Lifecycle/Registry/EventLoop/Scheduler/Supervisor/
HotReload) — по одной фазе, по отдельной команде.
