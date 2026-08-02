---
tags: [kroft, bootstrap, kernel, roadmap, epic, program]
created: 2026-07-31
status: draft
version: 2.0
author: Hermes (senior software architect) + Nikita (architecture direction)
depends_on: [ADR-018, ADR-019]
summary: >-
  Bootstrap Initiative v2 — Master Roadmap развития ядра KROFT_OS. 12 фаз
  (A–L). Каждая фаза имеет Goal / Components / Guardrails / Definition of Done /
  Smoke tests. Цель — непрерывный Runtime без «параллельного мира» (урок main.py).
---

# Bootstrap Initiative v2 — Master Roadmap (развитие ядра ОС)

> Статус: **draft** (2026-07-31). Программа развития ядра поверх закрытых 14 волн.
> Phase A (Composition Root, ADR-018) — **готова**. Phase B опирается на контракт
> **ADR-019 (Kernel Runtime Architecture)**. Все фазы B–L — только план до
> утверждения; код пишется по одной фазе, по отдельной команде, с собственным
> DoD/Guardrails/Smoke.
>
> **Главный урок, который эта программа предотвращает:** `main.py` (legacy) жил
> параллельно с платформами волн 11–14 и не знал о них. Чтобы этого не повторилось,
> каждая фаза имеет явные **Guardrails** (что ядро НЕ знает) и **Smoke-тесты**
> (что доказывает готовность до объявления фазы закрытой).

## 0. Граф развития (общий)

```
Bootstrap (A)
    │
    ▼
Kernel Runtime API (B)         ← фундамент: KernelRuntime + RuntimeState FSM
    │
    ▼
Lifecycle Manager (C)          ← IServiceLifecycle, единый контракт жизни
    │
    ▼
Process Registry (D)           ← единый реестр процессов (НЕ DependencyContainer)
    │
    ▼
Runtime Event Loop (E)         ← while running: poll/scheduler/registry/supervisor/metrics
    │
    ▼
Graceful Shutdown (F)          ← STOPPING → save → dispose → STOPPED (+ сигналы)
    │
    ▼
Supervisor / Watchdog (G)      ← heartbeat/health/restart/backoff/panic
    │
    ▼
Hot Reload (H)                 ← reload config/plugin/workflow/policy/adapter без остановки
    │
    ▼
Service Isolation (I)          ← own context/logger/metrics/config/event-namespace
    │
    ▼
Observability (J)              ← Runtime Dashboard (processes/cpu/mem/queue/health/…)
    │
    ▼
Distributed Runtime (K)        ← Desktop/Server/Cluster на одном ядре (remote registry)
    │
    ▼
Production Hardening (L)       ← chaos/stress/leak/deadlock/fault-injection/long-run
```

Сверху вниз: сначала **фиксируем API ядра** (B), потом наполняем жизнью.
`Runtime API` (B) выделен отдельно — это фундамент, от которого зависят C–L.

## 1. Фазы

---

### Phase A — Composition Root ✅ (готово)

См. **ADR-018**. `bootstrap.py` собирает DI-контейнер, поднимает адаптеры
(OmniRoute|Mock fallback), стартует платформы волн 11–14 как одноразовый вход.
**Не является Runtime** (вызывает `agent.ask()` один раз → exit). Точка передачи
управления `KernelRuntime` появляется в Phase B.

---

### Phase B — Kernel Runtime API

**Goal.** Создать единственный объект `KernelRuntime` — настоящее ядро. Bootstrap
делегирует ему управление.

```
bootstrap.py → KernelRuntime → Platforms
```

**Создать** `runtime/`:
```
runtime/
  kernel_runtime.py     # KernelRuntime
  runtime_state.py      # RuntimeState (FSM)
  runtime_events.py     # ядерные события
  runtime_errors.py     # ядерные ошибки
  runtime_config.py     # конфиг ядра
  __init__.py
```

**KernelRuntime** (API, методы почти пустые в скелете Phase B):
```
class KernelRuntime:
    initialize()
    start()
    stop()          # alias/bridge к shutdown() по контракту ADR-019
    restart()
    pause()
    resume()
    shutdown()
    state() -> RuntimeState
    health() -> HealthReport
    services() -> List[ProcessHandle]
    metrics() -> MetricsSnapshot
```

**RuntimeState** (конечный автомат, НЕ bool):
```
INITIALIZING → READY → RUNNING → PAUSED → STOPPING → STOPPED
                                        ↘ FAILED
```
Никаких `running=True`. Только FSM.

**Guardrails.**
- `KernelRuntime` НЕ импортирует и НЕ знает: `OmniRouteAdapter`, `ILlm`,
  `Desktop*`, `API*`, `Knowledge*`, `Memory*`. Ядро знает ТОЛЬКО `IServiceLifecycle`
  (контракт из Phase C) и примитивы `IEventBus`/`IProcessRegistry`.
- Все платформы попадают в ядро через `ProcessRegistry` (Phase D), не через
  прямые импорты в `kernel_runtime.py`.
- `runtime/` — это НОВЫЙ пакет; он не нарушает arch-gate (только `contracts.*` +
  примитивы; composition root инъектирует конкретику).

**Definition of Done.**
- Пакет `runtime/` создан; `KernelRuntime` реализует ВСЕ методы из API (тела могут
  быть минимальными: `start()` переводит FSM `INITIALIZING→READY→RUNNING`,
  `state()` возвращает текущий FSM-статус, цикл ещё не крутится).
- `RuntimeState` — FSM без булевых флагов состояния.
- Arch-gate зелёный (3 passed); `kernel_runtime.py` не импортирует adapters/сервисы
  напрямую (проверяется `test_services_do_not_cross_import` + новым
  `test_runtime_layer_isolation`).

**Smoke.**
```
KernelRuntime.start()  → READY → RUNNING
KernelRuntime.stop()   → STOPPED
KernelRuntime.state()  == RUNNING (после start) / STOPPED (после stop)
```
Ad-hoc: реальный прогон `bootstrap.py` с `KernelRuntime` в ядре печатает
`Kernel started` / `Runtime ready`, FSM в `RUNNING`.

---

### Phase C — Lifecycle Manager

**Goal.** Закрыть пробел: существующий `contracts/i_service.py::IService` имеет
только `name/initialize/execute`. Добавить полноценный жизненный цикл.

**Новый контракт `IServiceLifecycle` (расширяет `IService`):**
```
initialize()
start()
ready() -> bool
pause()
resume()
stop()
dispose()
```

**LifecycleManager** (управляет всеми процессами):
```
initialize all → start all → ready all → pause all → resume all → stop all → dispose all
```

**Service Status** (FSM каждого сервиса):
```
CREATED → INITIALIZED → STARTING → READY → RUNNING → PAUSED → STOPPING → STOPPED → FAILED → DISPOSED
```

**Guardrails.**
- Платформа сама НЕ управляет своим циклом — только `LifecycleManager` (через
  `KernelRuntime`) вызывает `initialize→start→ready→stop→dispose`.
- `ready()` — идемпотентный predicate, не переводит состояние, только сообщает.
- `pause()/resume()` не теряют состояние сервиса (не равно `stop/dispose`).

**Definition of Done.**
- `IServiceLifecycle` добавлен в `contracts/`; все платформы (Agent/Memory/Knowledge/
  Workflow/Optimization/Learning/Desktop/API) реализуют его.
- `LifecycleManager` переводит пул процессов через весь FSM по одной команде.
- Состояние каждого сервиса трекается в `ProcessRegistry` (Phase D).

**Smoke.**
```
10 сервисов → LifecycleManager.start() → 10 READY
LifecycleManager.pause()  → 10 PAUSED
LifecycleManager.resume() → 10 RUNNING
LifecycleManager.stop()   → 10 STOPPED
```

---

### Phase D — Process Registry

**Goal.** Устранить пробел: `DependencyContainer` хранит инстансы, но НЕ управляет
жизненным циклом. Создать `ProcessRegistry` — единый реестр процессов.

**Новый объект `ProcessRegistry`:**
```
ProcessRecord:
    uuid, name, type, owner, status, started_at, restarts, health, dependencies
```

**Registry умеет:**
```
register()  remove()  find()  list()  restart()  kill()  dependencies()
```

**Guardrails.**
- `ProcessRegistry` НЕ инстанцирует сервисы (это делает composition root /
  `KernelRuntime.initialize`). Registry только трекает handles + состояние.
- `ProcessRegistry` ≠ `DependencyContainer`. Container — локатор зависимостей;
  Registry — владелец жизненного цикла и состояния процессов.
- `restart()/kill()` делегируют `LifecycleManager`, не делают логику сами.

**Definition of Done.**
- `ProcessRegistry` реализован; каждый процесс имеет `uuid` + FSM-статус.
- Все платформы зарегистрированы при boot; `list()` возвращает полный снимок.
- `restart()/kill()` корректно меняют статус через LifecycleManager.

**Smoke.**
```
register 10 процессов → list() == 10
kill(pid) → status STOPPED
restart(pid) → status RUNNING, restarts += 1
dependencies(pid) → список зависимостей
```

---

### Phase E — Runtime Event Loop

**Goal.** Исправить пробел: `IEventBus` push-only (нет `poll()`), цикл невозможен.
Сделать непрерывный loop ядра.

**Kernel получает:**
```
while kernel.running:
    EventBus.poll()
    Scheduler.tick()
    Registry.monitor()
    Supervisor.watch()
    Metrics.flush()
    sleep()
```

**Добавить в `IEventBus`:**
```
poll(timeout)        # НОВОЕ
priority queue      # НОВОЕ
backpressure        # НОВОЕ
```
`Scheduler` становится **частью Runtime Loop**, не отдельным сервисом
(`services/scheduler.py::SchedulerService` уже реализован — вписывается, не пишется
заново; ядро вызывает `tick()`).

**Guardrails.**
- Цикл принадлежит ТОЛЬКО `KernelRuntime`. Платформы не крутят собственные loop'ы.
- `poll(timeout)` НЕ блокирует вечно (таймаут обязателен).
- `backpressure` не даёт очереди расти бесконечно (drop/возврат ошибки при переполнении).
- В теле цикла — только примитивы оркестрации; никакой платформенной логики
  (LLM/desktop/api) внутри loop body.

**Definition of Done.**
- `IEventBus.poll(timeout)` реализован (+ priority queue + backpressure).
- `KernelRuntime` в `RUNNING` крутит цикл; `stop()` корректно выходит из `while`.
- `Scheduler.tick()` вызывается в цикле; события доходят до подписчиков.

**Smoke.**
```
start() → RUNNING, loop тикает (счётчик тиков растёт)
publish(event) → loop доставляет подписчику (через poll)
stop() → выход из while, state STOPPED
```

---

### Phase F — Graceful Shutdown

**Goal.** Shutdown — не `Ctrl+C`-убийство процесса, а упорядоченное завершение.

```
STOPPING → stop scheduler → stop event bus → save runtime → dispose services → STOPPED
```

Поддержка `SIGINT` / `SIGTERM` / Windows Console Control Handler.

**Guardrails.**
- Никакого `sys.exit()` без сохранения состояния.
- `dispose()` сервисов — ПОСЛЕ `save runtime`.
- Сигналы обрабатываются обработчиком, который ставит FSM в `STOPPING` (не рвёт
  цикл мгновенно).

**Definition of Done.**
- `KernelRuntime.shutdown()` переводит `RUNNING→STOPPING→STOPPED` в заданном порядке.
- `SIGINT`/`SIGTERM` перехватываются → trigger shutdown (Unix + Windows).
- Состояние ядра сохранено до `dispose`.

**Smoke.**
```
start() → RUNNING
послать SIGINT (или Windows Console Ctrl-C) → STOPPING → ... → STOPPED
файл состояния ядра существует и валиден
все сервисы DISPOSED
```

---

### Phase G — Supervisor / Watchdog

**Goal.** Автовосстановление. `Watchdog → HealthMonitor → Supervisor`.

```
FAILED → Supervisor.restart()  or  Supervisor.disable()
```

**Новый объект `Supervisor` умеет:**
```
heartbeat        # периодический пинг процессов
health           # агрегат метрик
restart          # перезапуск зависшего
backoff          # экспоненциальная задержка между рестартами
crash detection  # обнаружение падения
panic mode       # каскадное отключение при массовом сбое
```

**Guardrails.**
- `Supervisor` использует ТОЛЬКО `ProcessRegistry` + `health()`; не лезет в логику
  платформ.
- `restart` ограничен `backoff` — бесконечный crash-loop ЗАПРЕЩЁН (после N → `disable`,
  не `restart`).
- `panic mode` отключает каскад, а не вешает ядро.

**Definition of Done.**
- `Supervisor` интегрирован в Event Loop (Phase E): `Supervisor.watch()` в каждом тике.
- Внедрённый сбой процесса → `Supervisor.restart()` → `RUNNING`.
- Повторяющийся crash-loop → процесс `DISABLED` после N попыток (не бесконечно).

**Smoke.**
```
запустить процесс, принудительно убить → Supervisor.restart() → READY
искусственный crash-loop → после N рестартов → DISABLED (не бесконечно)
```

---

### Phase H — Hot Reload

**Goal.** Обновлять конфигурацию и компоненты БЕЗ остановки ядра.

```
reload config / plugin / workflow / policy / adapter   — без остановки KernelRuntime
```

**Guardrails.**
- `KernelRuntime` core НЕ трогается при reload (только swap handle в `ProcessRegistry`).
- `reload` валидирует схему ДО применения (откат при невалидном).
- Adapter reload не разрывает текущие in-flight запросы.

**Definition of Done.**
- Смена конфига → ядро подхватывает без рестарта (`state()` остаётся `RUNNING`).
- Swap адаптера (LLM/desktop) → без downtime для других процессов.

**Smoke.**
```
start() → RUNNING
изменить config (в файле/источнике) → reload → metrics отражают новое значение
KernelRuntime всё ещё RUNNING (PID/FSM не менялись)
```

---

### Phase I — Service Isolation

**Goal.** Каждый сервис — в собственном изолированном контексте.

```
own context / logger / metrics / config / event namespace
```

**Guardrails.**
- Нет общих мутабельных глобальных состояний между сервисами.
- Event-неймспейсы изолированы (`svc.agent.*` не виден `svc.desktop.*`).
- Config — scoped per-service, не глобальный dict.

**Definition of Done.**
- Каждый сервис получает инъекцию собственного context/logger/metrics/config/namespace.
- Шум/падение в сервисе A не «протекает» в B.

**Smoke.**
```
publish(event, namespace="agent") → только подписчики "agent" получают
logger сервиса A не пишет в logger сервиса B
```

---

### Phase J — Runtime Observability

**Goal.** Runtime Dashboard с живой телеметрией.

```
Processes / CPU / Memory / Queue / Health / Restart Count / Events/sec / Latency
```

**Guardrails.**
- Сбор метрик — неблокирующий (не влияет на loop).
- Dashboard — read-only (не мутирует состояние ядра).

**Definition of Done.**
- Dashboard отражает live-состояние всех процессов из `ProcessRegistry` + `metrics()`.
- `Metrics.flush()` в Event Loop наполняет дашборд.

**Smoke.**
```
start() → dashboard: N процессов RUNNING
kill одного → Restart Count++ (видно на дашборде)
Events/sec растёт при публикации событий
```

---

### Phase K — Distributed Runtime

**Goal.** Desktop / Server / Cluster на одном ядре.

```
Process Registry → Remote Registry → Remote Runtime
```

**Guardrails.**
- Локальный FSM и контракты НЕ меняются для distributed.
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

### Phase L — Production Hardening

**Goal.** Последний этап — отказоустойчивость в реальных условиях.

```
Chaos Testing / Stress Testing / Memory Leak Detection / Deadlock Detection /
Fault Injection / Recovery Testing / Long Running Tests
```

**Guardrails.**
- Тесты не разрушают prod-данные (изолированный стенд).
- Fault Injection — за флагом, не в обычном прогоне.

**Definition of Done.**
- Все suite (chaos/stress/leak/deadlock/fault/long-run) зелёные.
- Long-running прогон стабилен (нет утечек/дедлоков за 24h+).

**Smoke.**
```
прогнать chaos-сценарий (убийство случайного процесса) → Supervisor восстанавливает
состояние ядра консистентно после серии сбоев
```

---

## 2. Критерии завершения инициативы

Bootstrap Initiative считается **действительно завершённой** только при:

| Критерий | Результат |
|---|---|
| Единая точка входа | `bootstrap.py` передаёт управление `KernelRuntime` |
| Runtime | Непрерывный жизненный цикл без завершения процесса после одного запроса |
| Lifecycle | Все платформы реализуют единый контракт жизненного цикла (`IServiceLifecycle`) |
| Registry | Все процессы зарегистрированы и управляются через `ProcessRegistry` |
| Event Loop | Ядро обрабатывает события через цикл выполнения (`EventBus.poll`) |
| Recovery | `Supervisor` автоматически обнаруживает и восстанавливает сбои |
| Shutdown | Корректное завершение всех процессов и сохранение состояния |
| Hot Reload | Обновление конфигурации и компонентов без полной перезагрузки |
| Observability | Полная телеметрия состояния Runtime |
| Production | Длительные стресс-тесты и сценарии отказоустойчивости проходят |

## 3. Связь с ADR

- **ADR-018** — Bootstrap Initiative, Phase A (Composition Root). `in_progress`.
- **ADR-019** — Kernel Runtime Architecture (контракт ядра: `KernelRuntime`,
  `IServiceLifecycle`, `IProcessRegistry`, `IEventBus.poll`, `IWatchdog`). База для
  фаз B–H.
- **Этот документ** — Master Roadmap программы (фазы A–L с DoD/Guardrails/Smoke).
  Не является волной; развивает само ядро ОС.

## 4. Дисциплина (чтобы не повторить урок main.py)

1. Каждая фаза B–L утверждается отдельно (код пишется только после утверждения).
2. Каждая фаза закрывается ТОЛЬКО при выполнении своего DoD + прохождении Smoke.
3. Guardrails каждой фазы проверяются арх-гейтом и выделенными тестами изоляции.
4. Ни одна фаза не добавляет «параллельный мир»: всё идёт через `KernelRuntime` +
  `ProcessRegistry` + `IServiceLifecycle`.
