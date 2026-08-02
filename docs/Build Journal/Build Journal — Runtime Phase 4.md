---
tags: [kroft, build-journal, runtime, phase-4, recovery, supervisor]
created: 2026-08-01
author: Hermes (senior software architect)
depends_on: [ADR-020 — Runtime Host Architecture, KROFT_OS Master Development Plan v2.0, Build Journal — Runtime Phase 3, Build Journal — Runtime Phase 2, Build Journal — Runtime Phase 1]
summary: >-
  Build Journal — Runtime Phase 4 (Autonomous Runtime Recovery Layer). Перевод из
  Observe→Report в Observe→Decide→Recover→Verify. ProcessState (9 состояний),
  policy-driven Backoff, IComponentController (Supervisor не строит инстансы, LAW K8),
  Panic levels 1/2/3, Recovery Journal. 5 тестов DoD (Test1 FAILED→RUNNING, Test2
  loop→QUARANTINED, Test3 panic→snapshot+stop, Test4 LAW K8, backoff policy-driven).
  Arch-gate зелёный, regression 750 passed.
---

# Build Journal — Runtime Phase 4 (Autonomous Runtime Recovery Layer)

> Дата: 2026-08-01. Продолжение Phases 1–3 (2182c5b, b50f4db, 8327666).
> Phase 4: Autonomous Runtime Recovery — Hermes OS переходит из режима
> Observe→Report в Observe→Decide→Recover→Verify.

## Что реализовано

### 1. ProcessState machine (расширение контракта)
- `contracts/i_process.py`: `ProcessState` (9 состояний): REGISTERED, STARTING,
  RUNNING, DEGRADED, STOPPING, STOPPED, FAILED, RECOVERING, QUARANTINED.
  `ProcessStatus` сохранён как alias (обратная совместимость Phase 2/3).
- `runtime/i_process_impl.py`: `Process` моделирует FSM. `start()` →
  REGISTERED→STARTING→RUNNING. Падение в run-loop → FAILED (не silently).
  `restart()` → RECOVERING→RUNNING (или False если QUARANTINED). **Не строит
  инстансы** (LAW K8 — Supervisor через IComponentController rebuild'ит).
- `runtime/component_registry.py`: `activate_platform` ставит REGISTERED→RUNNING;
  добавлен `reactivate(name, instance)` — НО registry не строит instance сам
  (instance приходит от IComponentController). `set_instance_builder` инжектится
  composition root'ом.

### 2. Policy-driven Backoff (не зашито в код)
- `runtime/recovery/backoff.py`: ConstantBackoff / LinearBackoff / ExponentialBackoff.
- `runtime/recovery/policy.py`: `RecoveryPolicy` (frozen dataclass, из dict/YAML):
  `restart`, `max_attempts`, `initial_delay`, `max_delay`, `strategy`.
- `runtime/recovery/strategy.py`: фабрика `build_strategy(policy)`.
- Примеры политик (из спеки): Database max_attempts=10, LLM Worker=3,
  Human approval restart=false.

### 3. IComponentController (Supervisor не знает как строится объект)
- `contracts/i_process.py`: `IComponentController.restart(name) -> bool`.
- `bootstrap_v2.py`: `ComponentController(IComponentController)` — конкретная
  реализация (composition root). `restart()` делегирует `ComponentRegistry.
  reactivate(name, instance)`, где instance строит `InstanceBuilder`. **Supervisor
  видит только порт** — не знает manifest/platform/location (LAW K8 сохранён).

### 4. Panic Handler (уровни аварии)
- `runtime/supervisor/exceptions.py`: ComponentFailure (L1), RuntimeFailure (L2),
  KernelPanic (L3).
- `contracts/i_kernel.py` + `kernel/kernel.py`: `panic(reason)` — snapshot +
  FAILED + emit `kernel.panic` + stop. `LifecycleState` +FAILED.
- `runtime/signal_handler.py`: SIGINT/SIGTERM → `kernel.panic()` (Level 3).
- Уровни: L1 component exception → Supervisor.restart; L2 runtime exception →
  snapshot+recovery; L3 kernel panic → emergency shutdown.

### 5. Recovery Journal (обязательное дополнение)
- `runtime/recovery/recovery_journal.py`: append-only JSONL. Запись на каждое
  восстановление: {component, failure, attempt, timestamp, result}. Основа
  самоанализа ("MetricsService падает каждые 3 дня после 6ч работы").

### 6. SupervisorService + HealthMonitor
- `runtime/supervisor/supervisor_service.py`: подписан на `component.failure` /
  `runtime.failure` / `kernel.panic`. `recover()` → policy-driven backoff →
  `controller.restart()` → RECOVERING→RUNNING или QUARANTINED. Пишет в Journal.
- `runtime/supervisor/health_monitor.py`: observe-only скан registry, публикует
  `health.unhealthy`. Не мутирует компоненты.
- `runtime/supervisor/recovery_policy.py`: `RecoveryPolicyRegistry` (component→policy).

## Какие файлы изменены

Созданы:
- `contracts/i_process.py` (+ProcessState/IComponentController/IHealthCheck),
  `contracts/i_kernel.py` (+panic, +FAILED), `contracts/__init__.py`
- `kernel/kernel.py` (+panic, LifecycleState+FAILED)
- `runtime/i_process_impl.py`, `runtime/component_registry.py`,
  `runtime/signal_handler.py`, `runtime/__init__.py`
- `runtime/recovery/{backoff,policy,strategy,recovery_journal,recovery_state}.py` + `__init__.py`
- `runtime/supervisor/{supervisor_service,health_monitor,recovery_policy,exceptions}.py` + `__init__.py`
- `bootstrap_v2.py` (+ComponentController, SupervisorService, HealthMonitor wiring)
- `tests/test_phase4_recovery.py` (DoD Test1–4 + backoff)

Не изменены (LAW K3): `services/agent_platform.py` и все платформы волн 11–14.

## Какие тесты добавлены (DoD)

`tests/test_phase4_recovery.py` — 5 тестов:
- **Test 1**: Failing service → FAILED → RECOVERING → RUNNING ✅
- **Test 2**: Restart loop fail x6 (max_attempts=5) → QUARANTINED ✅
- **Test 3**: Kernel panic → snapshot + stop + event published ✅
- **Test 4**: LAW check — Supervisor НЕ импортирует services/adapters/plugins
  (только contracts/runtime) ✅
- Bonus: Backoff policy-driven (exponential 1/2/4/8/16) ✅

## Результаты Smoke

Ad-hoc verifier (tmp, удалён): 10/10 passed — ProcessState 9 states, ComponentController
имплементирует порт, Test1/Test2/Test3 пройдены, RecoveryJournal пишет, Backoff
policy-driven, LAW K8 clean для supervisor+recovery, arch-gate green.

## Результаты Regression

```
pytest tests/test_phase4_recovery.py -> 5 passed
pytest tests/test_architecture.py   -> 3 passed  (arch-gate GREEN, LAW K8 holds)
pytest tests/                       -> 750 passed, 15 skipped, 6 pre-existing failures
```
6 pre-existing failures — в untracked graph/semantic тестах (до сеанса, Track L/Phase 6).
Phase 4 НЕ добавил новых падений (745→750, +5 от новых тестов Phase 4).

## Обновлённые ADR

- **ADR-020** (accepted): Phase 4 доказал — Observe→Decide→Recover→Verify работает.
  Supervisor через IComponentController (не строит инстансы), policy-driven Backoff,
  Recovery Journal. Вариант б подтверждён: Kernel минимален, recovery — обычные
  компоненты Runtime через ComponentRegistry + порты.

## Оставшиеся риски

1. Pre-existing 6 failures в untracked graph/semantic — Track L (Legacy Cleanup).
2. `comp_registry` в bootstrap_v2 — отдельный от основного (Phase 2/3) registry;
   в продакшене Supervisor должен наблюдать ТОТ ЖЕ registry, что активировал
   компоненты (нужна связка в composition root — кандидат на Phase 7 Observability
   дашборд, где Supervisor читает реальный registry).
3. Backoff delay в SupervisorService пока вычисляется (`backoff_delay`) но НЕ
   применяется как sleep между попытками (restart синхронный). Для реального
   exponential backoff нужен async/threaded retry-loop (Phase 4 MVP — одна попытка
   recover() за вызов; оркестрация backoff — следующий шаг).

## Следующий этап

**Phase 5 — Hot Reload**: ConfigWatcher (watchdog FS) + policy_reloader →
ConfigApplier.propose()/apply() с approve (двухфазный commit, LAW K5). Или
**Phase 6 — Legacy Cleanup** (параллельно): удалить agent_service.py,
graph_query_engine.py, stubs/, 6 untracked тестов (снять 6 pre-existing failures).
