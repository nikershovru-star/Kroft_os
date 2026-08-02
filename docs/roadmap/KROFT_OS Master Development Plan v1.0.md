---
tags: [kroft, master, dev, plan, kernel, roadmap]
created: 2026-08-01
status: draft
version: 1.0
author: Hermes (senior software architect) + Nikita (architecture direction)
depends_on: [ADR-018, ADR-019, Kernel Review (Phase 0.5), Bootstrap Initiative v2 — Master Roadmap, KROFT_OS Master Roadmap v2 — 12 Levels + 3 Architecture Epics]
summary: >-
  KROFT_OS Master Development Plan v1.0 (draft, утверждается architecture direction).
  10 фаз развития ядра поверх shipped Roadmap v1.0. Каждая фаза: Goal / Components /
  Guardrails (изоляция ядра) / DoD / Smoke. Ритм: реализация → арх-аудит → итерация.
  Заземлено в ground truth: kernel/kernel.py реален, платформы 11–14 — библиотеки
  (нет lifecycle-методов), пакетный import-graph — DAG без циклов.
---

# KROFT_OS — Master Development Plan v1.0

> Статус: **draft** (2026-08-01). Утверждается architecture direction. Программа
> развития ядра поверх закрытых 14 волн + Kernel Review (Phase 0.5) + Bootstrap
> Initiative v2 + Master Roadmap v2. Каждая фаза (1–10) имеет собственные
> Goal / Components / Guardrails / DoD / Smoke — ровно как требовал урок
> «не повторять main.py vs платформы 11–14»: каждая фаза доказывает связь с
> предыдущей через Smoke-тест, а не создаёт параллельный мир.
>
> **Абсолютный принцип (сохранить во ВСЕХ фазах):** `Kernel` НЕ импортирует
> `services.agent_platform` / `adapters.emni_route_adapter` / `contracts.i_knowledge`
> и др. платформы. Ядро знает ТОЛЬКО `IServiceLifecycle` + `IProcess` + `IEventBus`
> (шина — собственность ядра, не платформ) + `ProcessRegistry` (не `DependencyContainer`).
> Платформы 11–14 попадают в ядро ЧЕРЕЗ wrapper-адаптеры (как процессы, не библиотеки).
>
> **Ground truth (из Kernel Review, НЕ выдумано):**
> - `kernel/kernel.py` УЖЕ реализует `Kernel` (FSM `LifecycleState` + `initialize/start/stop/emit/save`, владе专门 `IEventBus`).
> - Платформы волн 11–14 (`AgentPlatform`/`MemoryPlatform`/`KnowledgePlatform`/…) — grep
>   подтвердил: НЕТ НИ ОДНОГО lifecycle-метода (`start/stop/initialize/pause/resume`) →
>   **библиотеки**, не процессы.
> - Пакетный import-graph — **DAG без циклов** (ADR-019 cycle-detection: 0 violations).
> - `bootstrap.py` — one-shot entrypoint (Phase A, ADR-018), HE daemon-режима.
> - `:20128` (OmniRoute) — недоступен в smoke-тестах; MockAdapter — обязательный fallback.
> - Осиротевший код (`agent_service.py`, `graph_query_engine.py`, `stubs/`, `test_graph_*`)
>   живёт вне структуры волн 5–14.

## 0. Текущее состояние (ground truth)

| Что есть | Чего нет |
|---|---|
| 14 волн платформ (чистые порты + сервисы) | Запускаемого Runtime (ядро = библиотека, не процесс) |
| `kernel/kernel.py` (FSM + start/stop/则会emit) | `IServiceLifecycle` (платформы — библиотеки, не процессы) |
| `IEventBus` (шина событий) | `ProcessRegistry` (нет единого реестра процессов) |
| Arch-gate: 0 violations | Живого LLM backend (`:20128` недоступен) |
| `bootstrap.py` (one-shot entrypoint) | Daemon-режима (Kernel не тикает сам) |
| Осиротевший код (`agent_service.py`, `graph_query_engine.py`, `stubs/`, `test_graph_*`) | Интеграции платформ 11–14 в единый runtime |

**Критический урок (зафиксированный):** `main.py` (legacy) и платформы 11–14 жили в
параллельных мирах — `main.py` не знал о волнах 11–14. Этот план предотвращает
повторение: каждая фаза (1–10) имеет Smoke-тест, доказывающий, что новый код
**связан** с существующим, а не лежит отдельно (как `main.py` vs платформы).

## 1. Стратегические направления (4 вектора)

```
Вектор A: Kernel Runtime          ← сделать KROFT_OS запускаемой ОС
Вектор B: Platform Integration    ← волны 11–14 как процессы в ядре
Вектор C: Production Hardening    ← надёжность, observability, chaos
Вектор D: External Runtime         ← OmniRoute, Distributed, Security
```

**Приоритет:** A → B → C → D.
- Без запускаемого ядра (A) нет смысла в интеграции (B).
- Без интеграции — нет смысла в харднинге (C).
- OmniRoute (D) — внешняя зависимость, НЕ блокер (MockAdapter покрывает 80% runtime-логики).

## 2. Детальный план по фазам

---

### Фаза 1 — Kernel Foundation (Level 1, Master Roadmap v2)

**Goal.** `Kernel` запускается как daemon, живёт своим циклом, штатно останавливается.

**Components (уже частично реализованы — НЕ с нуля):**
```
runtime/kernel_runtime.py      # точка входа: python -m runtime.kernel (расширяет kernel/kernel.py)
runtime/runtime_state.py       # единый FSM: INIT → READY → PAUSED → FAILED → STOPPING → STOPPED
runtime/signal_handler.py      # SIGINT/SIGTERM → graceful shutdown (Windows Console Ctrl-C)
runtime/__init__.py            # регистрация пакета runtime/
```

**Guardrails (сохранить принцип изоляции ядра).**
- `Kernel` НЕ импортирует `services.agent_platform`, `adapters.omni_route_adapter`,
  `contracts.i_knowledge` и др. платформы. Только `IServiceLifecycle` + `IProcess`
  + `IEventBus` + `ProcessRegistry` (контракты).
- `bootstrap.py` (ADR-018) передаёт управление `KernelRuntime.start()`, НЕ держит ссылку.

**Definition of Done.**
- `python -m runtime.kernel --mode=kernel-only` тикает 5 секунд без ошибок.
- Штатная остановка по SIGINT: все сервисы получают `stop()`, FSM → `STOPPED`.
- Arch-gate: 0 новых violations.

**Smoke.**
```bash
python -m runtime.kernel --mode=kernel-only &
sleep 2
kill -INT $!
# Ожидаем: лог "Kernel stopped", rc=0, нет traceback
```

---

### Фаза 2 — Process Registry (Level 2, Master Roadmap v2)

**Goal.** Платформы 11–14 регистрируются в ядре как процессы, не как библиотеки.

**Components.**
```
runtime/process_registry.py     # ProcessRegistry(IProcess) — НЕ DependencyContainer
runtime/wrappers/
  agent_platform_process.py        # AgentPlatformProcess(IServiceLifecycle) оборачивает AgentPlatform
  learning_platform_process.py     # LearningPlatformProcess(IServiceLifecycle) оборачивает ILearningStore
  optimization_platform_process.py # OptimizationPlatformProcess(IServiceLifecycle) оборачивает ConfigApplier
runtime/bootstrap_v2.py        # новый composition root: Kernel → Registry → обёртки → старт
```

**Guardrails (сохранить).**
- Существующие порты волн 11–14 (`IAgentPlatform`, `ILearningStore`, `IOptimizer`) НЕ
  модифицируются. Интеграция только через wrapper-адаптеры `IServiceLifecycle`.
- `ProcessRegistry` хранит `IProcess`, НЕ `AgentPlatform`. `Kernel` видит только
  `pid`, `status`, `start_time` (не саму платформу).
- `ProcessRegistry` ID — **UUID** (не PID), подготовка к Distributed Runtime (Фаза 9).

**Definition of Done.**
- `AgentPlatform` зарегистрирован в Registry как процесс со статусом `RUNNING`.
- `Kernel` может остановить `AgentPlatform` через `IServiceLifecycle.stop()`.
- Регресс волн 追问5–14: 225 passed / 10 skipped (не ломаем).
- Arch-gate: 0 violations.

**Smoke (Python).**
```python
# bootstrap_v2.py
kernel = KernelRuntime()
registry = ProcessRegistry()
registry.register("agent", AgentPlatformProcess(agent_platform))
kernel.start()
# Ожидаем: в логе "agent: RUNNING", "Kernel: READY"
kernel.stop()
# Ожидаем: "agent: STOPPED", "Kernel: STOPPED"
```

---

### Фаза 3 — Runtime Services (Level 3, Master Roadmap v2)

**Goal.** Инфраструктура ядра — метрики, конфиг, логирование, снапшоты.

**Components.**
```
runtime/services/metrics_service.py      # сбор метрик (CPU, память, queue depth)
runtime/services/config_service.py       # hot-read конфига из файла/ENV
runtime/services/snapshot_service.py     # дамп состояния Registry + FSM для отладки
runtime/services/logging_service.py      # структурированные логи (JSON, ротация)
```

**Guardrails.**
- Сервисы ядра НЕ зависят от платформ. Платформы публикуют метрики в `IEventBus` —
  сервисы подписаны.
- `ConfigService` читает файл, НО НЕ применяет его к runtime напрямую. Применение —
  через `ConfigApplier` (Wave 13, двухфазный commit).

**Definition of Done.**
- `MetricsService` публикует `metric:cpu` в EventBus каждые 5 сек.
- `SnapshotService` создаёт `snapshot_*.json` по запросу (через EventBus).
- Конфиг читается без перезапуска Kernel.

**Smoke (bash).**
```bash
# Kernel тикает  conditioner10 сек, собираем метрики
python -m runtime.kernel --mode=services &
sleep 10
# Проверяем: в логе есть metric:cpu, metric:memory
```

---

### Фаза 4 — Supervisor & Recovery (Levels 6–7, Master Roadmap v2)

**Goal.** Процесс падает → ядро рестартует его. Паника → ядро сохраняет состояние и умирает чисто.

**Components.**
```
runtime/supervisor.py       # SupervisorService: heartbeat, health check, restart policy (backoff)
runtime/recovery.py         # RecoveryPolicy: max restarts, panic threshold
runtime/health_check.py     # IHealthCheck порт: check(process) → HealthStatus
```

**Guardrails.**
- `Supervisor` НЕ знает `AgentPlatform`. Он знает `IProcess` и `IHealthCheck`.
- `Restart` — через `IServiceLifecycle.start()`, НЕ через `os.system()` или `subprocess`.
- Паника (N падений за T сек) → `Kernel` FSM → `FAILED` → snapshot → graceful stop.

**Definition of Done.**
- Искусственное падение `AgentPlatformProcess` (raise в `tick()`) → `Supervisor`
  рестартует с backoff 1s, 2s, 4s.
- 5 падений за 10 сек → Panic → `Kernel` → `FAILED` → snapshot → stop.
- Arch-gate: 0 violations.

**Smoke (Python).**
```python
# В тесте: процесс выбрасывает Exception в tick()
# Ожидаем: лог restart #1, #2, #3... затем PANIC → snapshot → Kernel STOPPED
```

---

### Фаза 5 — Hot Reload (Level 8, Master Roadmap v2)

**Goal.** Обновление конфига и политик без остановки Kernel.

**Components.**
```
runtime/hot_reload.py         # ConfigWatcher (watchdog на ФС)
runtime/policy_reloader.py    # трансляция изменений в Recommendation + ConfigApplier.propose()
```

**Guardrails.**
- Только `ConfigApplier` (Wave 13) мутирует runtime. Hot Reload генерирует
  `Recommendation`, но `apply()` требует `approve()` (двухфазный commit).
- НЕТ автоматического `apply()` без approve. Hot Reload = `propose()` + `notify()`, не `apply()`.
- Если approve НЕ дан за 5 минут — `Recommendation` истекает (`status → expired`).

**Definition of Done.**
- Меняем `policy.json` → `ConfigWatcher` ловит → генерирует `Recommendation` → proposed.
- Human (или Wave 14 Autonomy) approve → `ConfigApplier.apply()` → runtime обновлён.
- `Kernel` НЕ рестартовал. Регресс зелёный.

**Smoke (bash).**
```bash
# 1. Kernel running
echo '{"weights":{"reasoning":0.9}}' > config/policy.json
# 2. В логе: "HotReload: proposed rec-123 for policy:..."
# 3. approve через API/EventBus
# 4. В логе: "ConfigApplier: applied rec-123"
# 5. AgentPlatform использует новый вес БЕЗ рестарта
```

---

### Фаза 6 — Production Hardening (Level 12 + Epic L, Master Roadmap v2)

**Goal.** KROFT_OS работает 24+ часов без утечек, переживает хаос.

**Components.**
```
tests/chaos/              # ChaosMonkey: случайный kill процесса, дроп событий, задержка сети
tests/stress/             # StressRunner: 1000 агентов, 10K событий/сек
runtime/leak_detector.py  # LeakDetector: отслеживает рост памяти по процессам
```

**Guardrails.**
- Chaos-тесты работают на mock-адаптерах, НЕ ломают реальные данные.
- `LeakDetector` НЕ замедляет runtime > 5%.
- НЕ трогаем порты волн 5–14. Всё через `IProcess`/`IEventBus`.

**Definition of Done.**
- 24-часовой прогон: память растёт < 1%/час, CPU стабильный.
- Chaos: 100 итераций kill+recovery, 0 deadlock, 0 необработанных паник.
- Stress: 10K events/sec, latency p95 < 100ms (на mock-адаптерах).

**Smoke (bash).**
```bash
pytest tests/chaos/test_chaos_kernel.py -v
# Экспектируем: Siamese10 passed, 0 failed, 0 deadlock
```

---

### Фаза 7 — Legacy Cleanup (Debt Triage, завершение)

**Goal.** Осиротевший код удалён или явно помечен.

**Components (аудит).**
```
services/agent_service.py, services/graph_query_engine.py, stubs/,
tests/test_graph_*.py, tests/test_semantic_search.py
```
**Решение по каждому:** keep (переписать как процесс), migrate (в wrapper), delete (удалить).

**Guardrails.**
- НЕ удаляем без явного approve. Backup перед удалением.
- Если `agent_service.py` содержит полезную логику — мигрируем в
  `AgentPlatformProcess` (wrapper), НЕ в `AgentPlatform` (порт).
- `stubs/` — если используются тестами волн 5–14, оставляем. Если только
  осиротевшими тестами — удаляем.

**Definition of Done.**
- Нет файлов вне структуры (волны / runtime / tests / contracts).
- Или они явно в `legacy/` с README «не поддерживается, удалится в v2.1».
- `pytest tests/` — 0 failures (осиротевшие тесты удалены или починены).

**Smoke (bash).**
```bash
pytest tests/
# Экспектируем: N passed, 0 failed, 0 skipped (или skipped только live-gated)
```

---

### Фаза 8 — OmniRoute Integration (External Dependency)

**Goal.** Реальный LLM backend вместо mock.

**Components.**
```
adapters/omni_route_live.py  # живой OmniRouteAdapter(ILlm) с fallback на mock
runtime/connection_pool.py   # пул соединений к :20128, health check
bootstrap_v2.py --live       # флаг: использовать OmniRoute вместо MockAdapter
```

**Guardrails.**
- `OmniRouteAdapter` — в `adapters/`, реализует `ILlm`. НЕ в `services/`, НЕ в `kernel/`.
- Fallback: если `:20128` недоступен → `MockAdapter` + warning в лог.
- Timeout:  TRUE 5 сек на запрос, 3 retries с backoff.

**Definition of Done.**
- `bootstrap_v2.py --live` → реальный ответ от OmniRoute.
- `bootstrap_v2.py` (без флага) → `MockAdapter`, работает без `:20128`.
- Регресс зелёный в обоих режимах.

**Smoke (bash).**
```bash
# Предусловие: OmniRoute запущен на :20128
python bootstrap_v2.py --live --goal "2+2"
# Экспектируем: реальный ответ (через OmniRoute), лог "adapter: emni_route"
```

---

### Фаза 9 — Distributed Runtime (Level 11 + Epic K)

**Goal.** Несколько узлов KROFT_OS видят друг друга.

**Components.**
```
runtime/distributed/remote_registry.py  # RemoteProcessRegistry(IProcessRegistry)
runtime/distributed/cluster_node.py     # ClusterNode: heartbeat, election, partition
runtime/distributed/network_event_bus.py # NetworkEventBus(IEventBus) через TCP/WebSocket
```

**Guardrails.**
- Локальный `Kernel` НЕ знает о сети. Remote — через adapter.
- `ProcessRegistry` id — UUID (заложено в Фазе 2), работает на обоих узлах.
- `EventBus` сериализует только `contracts.*` entities (LAW 3: frozen, без live pointers).

**Definition of Done.**
- Два узла на `localhost:8001` и `localhost:8002` видят друг друга в `list_processes()`.
- Событие с узла A доходит до подписчика на узле B < 50ms.
- Partition (отключение сети) → узел помечает remote процессы `UNREACHABLE`, НЕ паникует.

**Smoke (bash).**
```bash
# Терминал 1
python -m runtime.kernel --node-id=alpha --port=8001
# Терминал 2
python -m runtime.kernel --node-id=beta --port=8002 --peer=localhost:8001
# Экспектируем: в логе обоих "peer connected: alpha/beta"
 ```

---

### Фаза 10 — Capability & Security (Epic C)

**Goal.** Процессы работают в sandbox с явными capabilities.

**Components.**
```
runtime/security/capability_manager.py  # CapabilityManager: выдача/проверка capabilities
runtime/security/sandbox.py             # Sandbox: ограничение ФС, сети, CPU
runtime/security/permission_policy.py   # PermissionPolicy: декларативные правила
```

**Guardrails.**
- `Kernel` НЕ проверяет permissions напрямую. Делегирует `CapabilityManager`.
- Capability — строка (`"file:read:/tmp"`, `"net:connect:localhost:20128"`), НЕ роль.
- `Sandbox` НЕ использует seccomp/namespaces (Python-уровень: monkeypatch `open`, `socket`).

**Definition of Done.**
- Процесс без capability `"file:write"` НЕ может писать в диск → `PermissionError`.
- Процесс с `"net:connect:localhost:20128"` может достучаться до OmniRoute.
- Попытка нарушения → `CapabilityDenied` → `Supervisor` логирует → НЕ паникует.

**Smoke (Python).**
```python
# Запускаем AgentPlatformProcess с capabilities=["event:publish"]
# Процесс пытается file:write → лог "CapabilityDenied: file:write"
# Процесс публикует event → OK
 ```

---

## 3. Расписание (Roadmap кварталов)

| Квартал | Фазы | Результат |
|---|---|---|
| Q1 | 1, 2, 3 | Kernel запускается, платформы 11–14 — процессы, runtime services живы |
| Q2 | 4, 5, 7 | Supervisor рестартует процессы, hot reload работает, legacy очищен |
| Q3 | 6, 8 | 24h прогон без утечек, OmniRoute интегрирован (если backend готов) |
| Q4 | 9, 10 | Distributed runtime (2+ узла), capability-based security |

**Внешние зависимости:**
- OmniRoute (`:20128`) — блокирует Фазу 8, НО НЕ блокирует Фазы 1–7. `MockAdapter`
  покрывает 80% runtime-логики.
- Host rename (`KnowledgeOS-v5` → `KROFT_OS`) — инфраструктура, НЕ блокер.

## 4. Дисциплина (ритм разработки)

Каждая фаза — отдельная команда, atomic commits, arch-аудит:

1. **Утверждение фазы** (ADR или дополнение к Master Roadmap)
2. **Реализация** (порты → сервисы → интеграция → тесты)
3. **Arch-аудит** (циклы? Kernel знает платформы? cross-layer imports?)
4. **Smoke-тест** (доказательство, что фаза работает с предыдущими)
5. **Коммиты** (1–4 атомарных, без `git add -A`)
6. **Регресс** (волны 5–14 + runtime)
7. **Переход к следующей фазе**

**Arch-гейт на каждой фазе:**
- 0 новых violations LAW 2
- DAG пакетных импортов остаётся ацикличным
- `Kernel` НЕ импортирует платформы напрямую

## 5. Риски и митигация

| Риск | Вероятность | Митигация |
|---|---|---|
| Wrapper-адаптеры платформ требуют изменения портов волн 11–14 | Средняя | Guardrail: порты неизменны. Если wrapper НЕ ложится — откладываем фазу, пишем ADR на расширение порта. |
| OmniRoute так и не поднимается | Низкая | `MockAdapter` покрывает 100% runtime-логики. OmniRoute — только адаптер, НЕ ядро. |
| Hot Reload ломает двухфазный commit Wave 13 | Средняя | Guardrail: Hot Reload только `propose()`, `apply()` требует approve. Автоматика запрещена. |
| Distributed Runtime требует сериализации live-объектов | Высокая | Guardrail: `EventBus` сериализует только frozen dataclasses из `contracts.*`. Никаких live pointers. |
| Legacy cleanup удалит нужный код | Низкая | Backup + explicit approve на каждый файл. НЕ удаляем, пока НЕ докажем, что тесты НЕ ломаются. |

## 6. Definition of Done всей программы (KROFT_OS v2.0)

- [ ] `python -m runtime.kernel` запускается как daemon, живёт, штатно останавливается
- [ ] Платформы 11–14 — процессы в Registry, Supervisor рестартует при падении
- [ ] Hot Reload конфига без рестарта (через `ConfigApplier`, с approve)
- [ ] 24h прогон без утечек, chaos tests пройдены
- [ ] OmniRoute интегрирован (fallback на mock)
- [ ] Distributed: 2+ узла обмениваются событиями
- [ ] Security: capability-based sandbox работает
- [ ] Arch-gate: 0 violations
- [ ] `pytest tests/`: 础0 failed, legacy удалён или помечен
- [ ] Git tag `v2.0.0`

**Вердикт архитектора:** План реалистичен, заземлён в текущем состоянии репо,
НЕ содержит фантазий (всё опирается на существующие порты). Фазы 1–3 критичны —
без них остальное бесполезно. OmniRoute — внешний блокер, НО НЕ критичный.

> **Статус документа:** `draft` (2026-08-01). Утверждается architecture direction.
> Код пишется только после утверждения конкретной фазы (по отдельной команде,
> с собственным DoD/Guardrails/Smoke — как в Bootstrap Initiative v2).
