---
tags: [kroft, adr, runtime, host, kernel, architecture]
created: 2026-08-01
status: accepted
version: 1.0
author: Herm_RD (senior software architect) + Nikita (architecture direction)
depends_on: [ADR-018, ADR-019, Kernel Review (Phase 0.5), Master Development Plan v2.0 (вариант б, утверждён)]
summary: >-
  ADR-020 — Runtime Host Architecture (вариант б, утверждён). Фиксирует: Kernel
  остаётся минимальным (Runtime State / Lifecycle / Event Loop / DI / Event Bus /
  Clock / Process Registry API / Shutdown / Signals); Scheduler/Metrics/Config/Snapshot/
  Supervisor — обычные компоненты Runtime через ComponentRegistry, НЕ wrapper'ы.
  Уже реализованный `kernel/kernel.py` НЕ удаляется и НЕ дублируется. Manifest-based
  Components, Event Runtime, Configuration Runtime. Без параллельного мира (урок main.py).
---

# ADR-020 — Runtime Host Architecture (Architecture Freeze)

> Статус: **accepted** (2026-08-01). Утверждён архитектурный вариант **(б)**:
> Runtime Host + Component Registry + Plugin Runtime вместо Wrapper Architecture.
> Не дублирует существующий `kernel/kernel.py`. План переписан под компонентную
> модель (Master Development Plan v3.0). Без параллельного мира (урок main.py).

## 1. Контекст

Вариант **(б)** официально утверждён (решение пользователя). KROFT_OS развивается
от библиотеки платформ к запускаемой AI-среде НЕ через `AgentPlatformWrapper /
LearningWrapper / …` (классический smell десятков wrapper'ов), а через
**Manifest-based Components** в `ComponentRegistry`.

**Уже сделано (ground truth из Kernel Review, НЕ трогаем):**
- `kernel/kernel.py` — реализованный `Kernel` (FSM `LifecycleState` + `initialize/start/stop/emit/save`, владеет `IEventBus`).
- Платформы волн 11–14 (`AgentPlatform`/`MemoryPlatform`/`KnowledgePlatform`/…) — **библиотеки** (grep подтвердил: НЕТ lifecycle-методов `start/stop/initialize/pause/resume`).
- Пакетный import-graph — **DAG без циклов** (arch-gate: 0 violations).
- `bootstrap.py` — one-shot entrypoint (ADR-018, Phase A), НЕ daemon.

**Чего нет (AS-IS, цель программы):**
- Runtime-процесса (Kernel не тикает сам).
- `IServiceLifecycle` (платформы — библиотеки, не процессы).
- `ProcessRegistry` (нет единого реестра).
- Distributed / Security / Observability / Hot Reload.

## 2. Решение (Architecture Freeze)

### 2.1 Kernel остаётся минимальным

`Kernel` содержит ТОЛЬКО:
```
Runtime State      # FSM (INIT → READY → RUNNING → STOPPED, + PAUSED/FAILED/STOPPING)
Lifecycle          # переходы состояний (initialize/start/stop/restart/pause/resume)
Event Loop         # основной цикл (while running: bus.poll(); scheduler.tick(); …)
DI                 # DependencyContainer (composition root)
Event Bus          # IEventBus (шина — собственность ядра, НЕ платформ)
Clock              # таймеры / sleep_fn / clock
Process Registry API# register/get/list/kill по IProcess (pid=uuid4, не PID ОС)
Shutdown           # SIGINT/SIGTERM → graceful
Signals            # обработчик сигналов ОС
```
**НЕТ внутри Kernel:** Scheduler, Metrics, Config, Snapshot, Supervisor, Dashboard, Security.
Они — **обычные компоненты Runtime** через `ComponentRegistry`.

### 2.2 Runtime Host вместо Wrapper Architecture

Вместо `AgentPlatformWrapper → AgentPlatform → Registry → Kernel` (цепочка обёрток):
```
plugins/
  agent/manifest.yaml        # id, version, capabilities, dependencies, entrypoint, healthcheck
  knowledge/manifest.yaml
  learning/manifest.yaml
  optimization/manifest.yaml
  desktop/manifest.yaml
  api/manifest.yaml
  scheduler/manifest.yaml
  metrics/manifest.yaml
  config/manifest.yaml
  snapshot/manifest.yaml
  supervisor/manifest.yaml
```
`Runtime` делает `discover() → load() → validate() → activate()` — НЕ `register()×N` вручную.
**Никаких отдельных wrapper'ов** (десятки файлов `XxxWrapper` повторяющих `start/stop/status/health`).

### 2.3 Component Registry (не ProcessRegistry)

`ComponentRegistry` загружает компоненты по манифестам. Платформы 11–14 интегрируются
как **компоненты** (manifest-based), НЕ как процессы-библиотеки:
```
Component Registry
  ├── Agent Platform
  ├── Knowledge Platform
  ├── Learning Platform
  ├── Optimization Platform
  ├── Desktop Platform
  ├── API Platform
  ├── Scheduler Component
  Smart ├── Metrics Component
  Smart ├── Config Component
  Smart └── Snapshot Component
```
(все — компоненты Runtime, не процессы-библиотеки).

### 2.4 Plugin Runtime (вместо bootstrap.py register()×N)

```
plugins/agent/manifest.yaml → Runtime.discover() → load() → validate() → activate()
```
Загрузка компонентов автоматическая, без ручного `register()` в `bootstrap.py`.
**Не bootstrap.py → register()×N** (плохо масштабируется).

### 2.5 Scheduler / EventBus / Config — отдельные сервисы

- `Scheduler` — **НЕ часть Kernel**. Kernel вообще не знает Scheduler.
  `Scheduler` — обычный runtime-компонент (подписан на EventBus, получает TimerEvent).
- `IEventBus` принадлежит Kernel (шина — собственность ядра). Но `InMemoryEventBus` /
  `RedisEventBus` / `KafkaEventBus` / `NetworkEventBus` — отдельные реализации, НЕ внутри Kernel.
- `Configuration` — отдельная подсистема (Sources: ENV/json/yaml/Vault/Remote → Validation → Change Set → Apply → Rollback), НЕ размазана по ядру.

## 3. Guardrails (LAW K1–K7, адаптированные под пересмотр)

| Закон | Суть | Проверка |
|---|---|---|
| **LAW K1** | Kernel импортирует только `contracts.i_kernel`, `contracts.i_process`, `contracts.i_event_bus`, `runtime.*`. НИКОГДА `services.agent_platform`, `adapters.emni_route_adapter`, `contracts.i_knowledge`. | Arch-gate AST-scan |
| **LAW K2** | `ComponentRegistry` хранит компоненты, НЕ конкретные платформы. Kernel видит `pid`, `status`, `start_time`. | Type-check + unit-test |
| **LAW K3** | Платформы 11–14 НЕ модифицируются. Интеграция только через ComponentRegistry (manifest-based), НЕ wrapper-адаптеры. | Diff-check: 0 изменений в `services/agent_platform.py` и т.д. |
| **LAW K4** | `IEventBus` принадлежит Kernel. Платформы subscribe/publish, НЕ создают шину. | Import-check |
| **LAW K5** | Mutation runtime только через `ConfigApplier` (Wave 13). Hot Reload = `propose()`, `apply()` требует approve. | Integration-test + code-review |
| **LAW K6** | Каждая фаза имеет Smoke-тест, доказывающий связь с предыдущей. Параллельных миров (как main.py) — нет. | Smoke-test gate |
| **LAW K7** | Atomic commits. Без `git add -A`. | Git hook + review |

## 4. Consequences

- **Положительные:** Ядро остаётся минимальным; функциональность — через подключаемые
  компоненты (manifest-based). KROFT_OS растёт за счёт новых проектов (KnowledgeOS, MarketMind,
  Desktop, API, Agents, Marketplace, Distributed) без расширения самого ядра.
- **Отрицательные:** Требует переписывания Master Dev Plan v2.0 → v3.0 (компонентная модель
  вместо процессной). Но уже сделанное (`kernel/kernel.py`, платформы-библиотеки) сохраняется.
- **Архитектурный урок main.py:** `kernel/kernel.py` НЕ дублируется; платформы 11–14 не
  становятся wrapper'ами — они грузятся через `ComponentRegistry` как компоненты.

## 5. Статус документа

**accepted** (2026-08-01). Утверждён вариант **(б)**. Архитектура заморожена. Следующий
шаг — реализация по переписанному плану (Master Dev Plan v3.0), поверх существующего
`kernel/kernel.py`, без создания второго ядра.

> **Вердикт:** План реалистичен, заземлён в текущем состоянии репо (Kernel Review), НЕ
> содержит фантазий. Фазы 1–3 критичны (Foundation → Runtime Host → Plugin Runtime) — без
> них остальное бесполезно, но теперь в контексте компонентной модели, а не Wrapper Architecture.
