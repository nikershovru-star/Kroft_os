---
tags: [kroft, master, dev, plan, v3, runtime, host]
created: 2026-08-01
status: draft
version: 3.0
author: Hermes (senior software architect) + Nikita (architecture direction)
depends_on: [ADR-018, ADR-019, Kernel Review (Phase 0.5), Master Development Plan v2.0, KROFT_OS Master Development Plan v1.0, ADR-020 — Runtime Host Architecture]
summary: >-
  KROFT_OS Master Development Plan v3.0 (draft, утверждён вариант б). Переписан
  под компонентную модель: Runtime Host → Component Registry → Plugin Runtime вместо
  Wrapper Architecture. Каждая фаза: Goal / Components / Guardrails / DoD / Smoke.
  Kernel остаётся минимальным; Scheduler/Metrics/Config/Supervisor — компоненты
  Runtime через ComponentRegistry. Уже реализованный kernel/kernel.py НЕ удаляется.
---

# KROFT_OS — Master Development Plan v3.0 (Runtime Host Architecture)

> Статус: **draft** (2026-08-01). Утверждён архитектурный вариант **(б)** (ADR-020).
> План переписан под компонентную модель (НЕ Wrapper Architecture). Каждая фаза имеет
> собственные Goal / Components / Guardrails (изоляция ядра) / DoD / Smoke — ровно как
> требовал урок «не повторять main.py vs платформы 11–14»: каждая фаза доказывает связь
> с предыдущей через Smoke-тест, а не создаёт параллельный мир.
>
> **Абсолютный принцип (сохранить во ВСЕХ фазах, адаптированный под пересмотр):**
> `Kernel` НЕ импортирует `services.agent_platform` / `adapters.emni_route_adapter` /
> `contracts.i_knowledge` и др. платформы. Ядро знает ТОЛЬКО `IServiceLifecycle` +
> `IProcess` + `IEventBus` (шина — собственность ядра) + `ProcessRegistry` (теперь
> `ComponentRegistry`) — компоненты, НЕ процессы-библиотеки.
>
> **Ground truth (из Kernel Review + ADR-020, НЕ выдумано):**
> - `kernel/kernel.py` УЖЕ реализует `Kernel` (FSM `LifecycleState` + `initialize/start/stop/emit/save`, владеет `IEventBus`).
> - Платформы волн 11–14 (`AgentPlatform`/`MemoryPlatform`/`KnowledgePlatform`/…) — grep подтвердил: НЕТ lifecycle-методов → **библиотеки**, не процессы.
> - Пакетный import-graph — **DAG без циклов** (arch-gate: 0 violations).
> - `bootstrap.py` — one-shot entrypoint (ADR-018, Phase A), НЕ daemon.

## 0. Текущее состояние (ground truth, переписанное под компонентную модель)

| Что есть | Чего нет (цель программы) |
|---|---|
| 14 волн платформ (чистые порты + сервисы) | Запускаемого Runtime (Kernel не тикает сам) |
| `kernel/kernel.py` (FSM + start/stop/emit) | `IServiceLifecycle` (платформы — библиотеки, не компоненты) |
| `IEventBus` (шина событий, владеет Kernel) | `ComponentRegistry` (нет единого реестра компонентов) |
| Arch-gate: 0 violations | Живого LLM backend (`:20128` недоступен) |
| `bootstrap.py` (one-shot entrypoint) | Daemon-режима (Kernel не тикает сам) |
| Осиротевший код (`agent_service.py`, `graph_query_engine.py`, `stubs/`, `test_graph_*`) | Интеграции платформ 11–14 как компонентов в единый runtime |

**Критический урок зафиксирован (main.py vs платформы 11–14 → НЕ повторяется):**
Вместо `AgentPlatformWrapper → AgentPlatform → Registry → Kernel` (цепочка обёрток)
используется `ComponentRegistry` (manifest-based): `plugins/agent/manifest.yaml → Runtime.discover() → load() → validate() → activate()`. Платформы 11–14 интегрируются как **компоненты**, НЕ как процессы-библиотеки. Никаких отдельных wrapper'ов (десятки файлов `XxxWrapper`).

## 1. Стратегические направления (4 вектора, адаптированные)

```
Вектор A: Runtime Host (Foundation → Runtime Host → Plugin Runtime)
Вектор B: Resilience (Supervisor, Configuration Runtime, Observability)
Вектор C: Production Hardening (Chaos/Stress, Distributed-ready)
Вектор D: External & Distributed (OmniRoute, Security, Marketplace)
```

**Приоритет:** A → B → C → D.
- Без запускаемого ядра (A) нет смысла в интеграции (B).
- Без интеграции — нет смысла в харднинге (C).
- OmniRoute (D) — внешняя зависимость, НЕ блокер (MockAdapter покрыва Fry 80% runtime-логики).

## 2. Детальный план по фазам (переупорядоченный roadmap из вашего пересмотра)

---

### Phase 0 — Architecture Freeze
**Goal.** Зафиксировать направление (вариант б утверждён, ADR-020 accepted).
**Components.** ADR-020 (Runtime Host Architecture), этот документ (Master Dev Plan v3.0), MOC-обновление.
**Guardrails.** Kernel остаётся минимальным (Runtime State / Lifecycle / Event Loop / DI / Event Bus / Clock / Process Registry API / Shutdown / Signals). Scheduler/Metrics/Config/Supervisor — компоненты Runtime через ComponentRegistry.
**Definition of Done.** Архитектура заморожена: документы (ADR-020 + MDP v3.0 + MOC) отражают компонентную модель, НЕ Wrapper Architecture.
**Smoke.** Документы резолвятся в MOC; ADR-020 статус accepted.

---

### Phase 1 — Foundation (minimal Kernel)
**Goal.** `Kernel` (уже из `kernel/kernel.py`) остаётся основой; добавить только Clock/Signals/Process Registry API.
**Components.** `runtime/kernel_runtime.py` (расширяет `kernel/kernel.py`, НЕ дублирует), `runtime/runtime_state.py` (FSM), `runtime/signal_handler.py` (SIGINT/SIGTERM).
**Guardrails (K1–K7).** Kernel НЕ импортирует платформы. Только `contracts.i_kernel` / `i_process` / `i_event_bus` / `runtime.*`.
**Definition of Done.** `python -m runtime.kernel --mode=kernel-only` тикает 5 сек без ошибок. SIGINT → FSM → STOPPED. Arch-gate: 0 violations.
**Smoke.** `python -m runtime.kernel --mode=kernel-only &` → `kill -INT` → лог "Kernel stopped", rc=0.

---

### Phase 2 — Runtime Host
**Goal.** `Runtime Host` загружает компоненты через `ComponentRegistry` (manifest-based).
**Components.** `runtime/component_registry.py` (IComponentRegistry), `runtime/runtime_host.py` (`discover() → load() → validate() → activate()`), `plugins/*/manifest.yaml`.
**Guardrails.** Платформы 11–14 интегрируются как компоненты (manifest), НЕ процессы-библиотеки. `ComponentRegistry` хранит компоненты, НЕ конкретные платформы.
**Definition of Done.** Agent/Kknowledge/Learning/Optimization/Autonomy компоненты зарегистрированы в ComponentRegistry как RUNNING. Kernel может остановить через `IServiceLifecycle.stop()`.
**Smoke.** `kernel = KernelRuntime(); registry = ComponentRegistry(); registry.register("agent", AgentPlatformComponent(...)); kernel.start()` → "agent: RUNNING".

---

### Phase 3 — Plugin Runtime
**Goal.** `plugins/` грузятся автоматически (НЕ `register()×N` вручную).
**Components.** `runtime/plugin_runtime.py`, `plugins/agent/manifest.yaml`, `plugins/knowledge/manifest.yaml`, … (все компоненты).
**Guardrails.** Никаких отдельных wrapper'ов. `Runtime` делает `discover() → load() → validate() → activate()`.
**Definition of Done.** Загрузка компонентов автоматическая; больше НЕТ цепочки `XxxWrapper`.
**Smoke.** `Runtime.discover()` находит манифесты → `load()` → `activate()` → компоненты RUNNING.

---

### Phase 4 — Event System
**Goal.** `IEventBus` принадлежит Kernel; отдельные реализации (`InMemoryEventBus` / `RedisEventBus` / `KafkaEventBus` / `NetworkEventBus`) — НЕ внутри Kernel.
**Components.** `runtime/event_runtime.py`, `adapters/event_bus_impl.py` (InMemory/Redis/Kafka/Network).
**Guardrails.** Kernel знает только `IEventBus`. `InMemoryEventBus` и др. — отдельные реализации (подсистемы), НЕ часть Kernel.
**Definition of Done.** События маршрутизируются через шину; Kernel публикует, компоненты подписаны.
**Smoke.** Publish/subscribe работает; Kernel НЕ создаёт шину сам.

---

### Phase 5 — Configuration Runtime
**Goal.** Отдельная подсистема (Sources: ENV/json/yaml/Vault/Remote → Validation → Change Set → Apply → Rollback), НЕ размазана по ядру.
**Components.** `runtime/config_runtime.py`, `runtime/config_sources.py`, `runtime/config_apply.py`.
**Guardrails.** ConfigApplier (Wave 13) мутирует runtime. Hot Reload = `propose()`, `apply()` требует approve.
**Definition of Done.** Меняем `config/policy.json` → `ConfigWatcher` ловит → `Recommendation` proposed → approved → applied. Kernel НЕ рестартовал.
**Smoke.** Hot Reload без рестарта; конфиг читается без перезапуска.

---

### Phase 6 — Component Runtime
**Goal.** Платформы 11–14 как компоненты (manifest-based), НЕ процессы-библиотеки.
**Components.** `runtime/component_runtime.py`, `plugins/*/manifest.yaml` (все платформы как компоненты).
**Guardrails.** Платформы НЕ модифицируются (LAW K3). Интеграция через ComponentRegistry (manifest), НЕ wrapper-адаптеры.
**Definition of Done.** Все платформы 11–14 загружаются как компоненты; Kernel управляет ими через ComponentRegistry.
**Smoke.** ComponentRegistry содержит все платформы; Kernel стартует их как компоненты.

---

### Phase 7 — Scheduler (Runtime Component)
**Goal.** `Scheduler` — НЕ часть Kernel. Обычный runtime-компонент (подписан на EventBus, получает TimerEvent).
**Components.** `runtime/scheduler_component.py`, `runtime/scheduler_tick.py`.
**Guardrails.** Kernel вообще НЕ знает Scheduler. Scheduler — компонент Runtime через ComponentRegistry.
**Definition of Done.** Scheduler тикает в цикле ядра (через EventBus), НЕ внутри Kernel.
**Smoke.** Scheduler получает TimerEvent → исполняет задачи; Kernel НЕ импортирует Scheduler.

---

### Phase 8 — Supervisor (Runtime Component)
**Goal.** Supervisor рестартует компоненты при падении (политики: Always/Never/OnFailure/Manual/Critical/Optional).
**Components.** `runtime/supervisor_component.py`, `runtime/recovery_policy.py`.
**Guardrails.** Supervisor НЕ знает платформ напрямую; знает `IProcess` + `IHealthCheck` (через ComponentRegistry).
**Definition of Done.** Искусственное падение компонента → Supervisor рестартует с backoff. Panic → Kernel FAILED → snapshot → stop.
**Smoke.** restart #1/#2/#3 → PANIC → snapshot → Kernel STOPPED.

---

 Phase 9 — Observability
**Goal.** Видимость внутри ОС: процессы, ресурсы, события, здоровье (как компоненты Runtime).
**Components.** `runtime/observability/`, `runtime/dashboard.py`, `runtime/event_logger.py`.
**Guardrails.** Сервисы ядра НЕ зависят от платформ; платформы публикуют метрики в EventBus (через ComponentRegistry), сервисы подписаны.
**Definition of Done.** Dashboard показывает таблицу процессов (pid, status, cpu%, memory, last_event). Alert на CPU > 80%.
**Smoke.** `python -m runtime.dashboard` выводит таблицу процессов, зелёные статусы.

---

### Phase 10 — Knowledge Runtime
**Goal.** Единая инфраструктура памяти/графа/поиска (Knowledge Platform — системообразующая часть, НЕ одна из платформ).
**Components.** `runtime/knowledge_runtime.py`, `runtime/memory_layer.py`, `runtime/embeddings.py`, `runtime/graph_layer.py`.
**Guardrails.** Agent НЕ знает, где лежат знания; обращается только к Runtime (через ComponentRegistry).
**Definition of Done.** Agent обращается к Runtime через ComponentRegistry; Knowledge — системообразующая часть (НЕ одна платформа).
**Smoke.** Agent резолвит Knowledge через Runtime (manifest), НЕ импортируя платформу напрямую.

---

### Phase 11 — Security (Capability, изоляция)
**Goal.** Процессы работают в sandbox с явными capabilities (строка, НЕ роль).
**Components.** `runtime/security/capability_manager.py`, `runtime/security/sandbox.py`, `runtime/security/permission_policy.py`.
**Guardrails.** Kernel НЕ проверяет permissions напрямую; делегирует CapabilityManager (через ComponentRegistry).
**Definition of Done.** Процесс без capability → PermissionError; процесс с capability → достучался до OmniRoute. Нарушение → CapabilityDenied (Supervisor логирует, НЕ паникует).
**Smoke.** Запуск компонента с capabilities; нарушение → CapabilityDenied лог.

---

### Phase 12 — Production (Hardening-ready)
**Goal.** 24/7 uptime proof (через Component Runtime + Supervisor + Config Runtime).
**Components.** `tests/chaos/`, `tests/stress/`, `runtime/leak_detector.py`.
**Guardrails.** Chaos/Stress работают на mock-адаптерах. LeakDetector НЕ замедляет runtime > 5%. Всё через ComponentRegistry.
**Definition of Done.** 24h прогон: память <  Omega%/час; Chaos 100 итераций kill+recovery, 0 deadlock.
**Smoke.** `pytest tests/chaos/test_chaos_kernel.py` → 10 passed.

---

### Phase 13 — Distributed Runtime (в конце)
**Goal.** Несколько узлов KROFT_OS видят друг друга (через ComponentRegistry + Remote Registry).
**Components.** `runtime/distributed/remote_registry.py`, `runtime/distributed/cluster_node.py`, `runtime/distributed/network_event_bus.py`.
**Guardrails.** Локальный Kernel НЕ знает о сети; Remote — через adapter (ComponentRegistry). EventBus сериализует только frozen dataclasses из `contracts.*`.
**Definition of Done.** Два узла localhost:8001/8002 видят друг друга. Событие A → B < 50ms. Partition → remote процессы UNREACHABLE, НЕ паника.
**Smoke.** `python -m runtime.kernel --node-id=alpha --port=8001` + `beta --port=8002 --peer=localhost:8001` → "peer connected".

---

## 3. Расписание (Roadmap кварталов, адаптированное)

| Квартал | Фазы | Результат |
|---|---|---|
| Q1 | 0, 1, 2, 3 | Architecture Freeze; Kernel (из kernel/kernel.py) — основа; Runtime Host загружает компоненты |
| Q2 | 4, 5, 6, 7 | Event System; Config Runtime; Component Runtime; Scheduler как компонент |
| Q3 | 8, 9, 10, 11 | Supervisor; Observability; Knowledge Runtime; Security (capability) |
| Q4 | 12, 13 | Production (Hardening-ready); Distributed (в конце) |

**Внешние зависимости:**
- OmniRoute (`:20128`) — блокирует Phase 9 (Distributed), НО НЕ блокирует Phase 0–7.
- Host rename (`KnowledgeOS-v5` → `KROFT_OS`) — инфраструктура, НЕ блокер.

## 4. Дисциплина (ритм разработки, адаптированный)

Каждая фаза — отдельная команда, atomic commits, arch-аудит (как в MDP v2.0, но под компонентную модель):
1. **Утверждение фазы** (ADR-020 или дополнение к Master Dev Plan v3.0)
2. **Реализация** (порты → сервисы → интеграция компонентов → тесты)
3. **Arch-аудит** (циклы? Kernel знает платформы? cross-layer imports? — через ComponentRegistry, НЕ wrapper)
4. **Smoke-тест** (доказательство, что фаза работает с предыдущей)
5. **Коммиты** (1–4 атомарных, без `git add -A`)
6. **Регресс** (волны 5–14 + runtime, адаптированный под компонентную модель)
7. **Переход к следующей фазе**

**Arch-гейт на каждой фазе (адаптированный):**
- Characteristic 0 новых violations LAW 2 (Kernel НЕ импортирует платформы)
- DAG пакетных импортов остаётся ацикличным (компоненты через ComponentRegistry, НЕ wrapper)
- `Kernel` НЕ импортирует платформы напрямую (только `contracts.i_kernel` / `i_process` / `i_event_bus` / `runtime.*`)

## 5. Риски и митигация (адаптированные)

| Риск | Вероятность | Митигация |
|---|---|---|
| ComponentRegistry требует изменения портов волн 11–14 | Средняя | Guardrail: порты неизменны. Если компонент НЕ ложится — откладываем фазу, пишем ADR на расширение порта (через ComponentRegistry, НЕ wrapper). |
| OmniRoute не поднимается | Низкая | MockAdapter покрывает 100% runtime-логики. OmniRoute — только адаптер, НЕ ядро. |
| Hot Reload ломает двухфазный commit Wave 13 | Средняя | Guardrail: Hot Reload только `propose()`, `apply()` требует approve. Автоматика запрещена. |
| Distributed требует сериализации live-объектов | Высокая | Guardrail: EventBus сериализует только frozen dataclasses из `contracts.*`. Никаких live pointers. |
| Legacy cleanup удалит нужный код | Низкая | Backup + explicit approve на каждый файл. НЕ удаляем, пока регресс НЕ зелёный. |

## 6. Definition of Done всей программы (KROFT_OS v3.0)

- [ ] `python -m runtime.kernel` запускается как daemon (поверх существующего `kernel/kernel.py`), живёт, штатно останавливается
- [ ] Платформы 11–14 — компоненты в ComponentRegistry, Supervisor рестартует при падении
- [ ] Hot Reload конфига без рестарта (через ConfigApplier, с approve)
- [ ] 24h прогон без утечек, chaos tests пройдены
- [ ] OmniRoute интегрирован (fallback на mock)
- [ ] Distributed: 2+ узла обмениваются событиями
- [ ] Security: capability-based sandbox работает
- [ ] Arch-gate: 0 violations (Kernel НЕ импортирует платформы)
- [ ] `pytest tests/`: 0 failed, legacy удалён или помечен
- [ ] Git tag `v3.0.0`

**Вердикт архитектора:** План реалистичен, заземлён в текущем состоянии репо (Kernel Review + ADR-020), НЕ содержит фантазий. Фазы 0–3 критичны (Foundation → Runtime Host → Plugin Runtime → Event System) — без них остальное бесполезно, но теперь в контексте компонентной модели (через ComponentRegistry), НЕ Wrapper Architecture.

> **Статус документа:** `draft` (2026-08-01). Утверждён вариант **(б)** (ADR-020 accepted). Код пишется только после утверждения конкретной фазы (по отдельной команде, с собственным DoD/Guardrails/Smoke — как в Bootstrap Initiative v2).
