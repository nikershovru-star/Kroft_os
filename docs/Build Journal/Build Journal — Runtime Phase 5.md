---
tags: [kroft, build-journal, runtime, phase-5, hot-reload, config]
created: 2026-08-01
author: Hermes (senior software architect)
depends_on: [ADR-020 — Runtime Host Architecture, KROFT_OS Master Development Plan v2.0, Build Journal — Runtime Phase 4, Build Journal — Runtime Phase 3, Build Journal — Runtime Phase 2, Build Journal — Runtime Phase 1]
summary: >-
  Build Journal — Runtime Phase 5 (Hot Reload). Замыкает цикл Observe→Decide→
  Recover→Verify: конфиг меняется → система применяет без полной перезагрузки.
  ConfigService следит за config.json (os.stat polling) → config.changed;
  ComponentController.swap() заменяет инстанс без Kernel.stop(); ComponentRegistry.
  reload_manifests() активирует новый плагин без рестарта; FileWatcher stdlib-only
  (без watchdog). 5 тестов DoD. Arch-gate зелёный, regression 755 passed.
---

# Build Journal — Runtime Phase 5 (Hot Reload)

> Дата: 2026-08-01. Продолжение Phases 1–4 (2182c5b, b50f4db, 8327666, 33ff6d1).
> Phase 5: Hot Reload — Hermes OS замыкает цикл. Phase 3 дал ConfigService
> (чтение без рестарта), Phase 4 дал Supervisor (recovery по событию). Hot Reload
> добавляет реакцию на изменение конфига/плагинов без полной перезагрузки.

## Что реализовано

### 1. Config hot-reload (Phase 3 → Phase 5)
- `runtime/services/config_service.py`: `start_watching()` polling `config.json`
  через **stdlib `os.stat`** (НЕ watchdog — third-party сломал бы arch-gate).
  При изменении → `reload()` + publish `config.changed` + `kernel.lifecycle`
  {type: config.reloaded}. Kernel НЕ модифицирован (LAW K3) — видит это как
  обычное lifecycle-событие.

### 2. Component swap (Supervisor → replace instance)
- `contracts/i_process.py`: `IComponentController.swap(name, new_instance)` порт.
- `bootstrap_v2.py`: `ComponentController.swap()` → `registry.swap(name, instance)`.
- `runtime/component_registry.py`: `swap(name, instance)` — `bind_instance` +
  `restart()` (RECOVERING→RUNNING) **без Kernel.stop()**. Деградированный
  компонент заменяется на новую версию на лету.

### 3. Manifest reload (new plugin activates live)
- `runtime/component_registry.py`: `reload_manifests()` — перечитывает
  `plugins/*/manifest.yaml`, активирует НОВЫЕ компоненты (через InstanceBuilder),
  существующие не трогает (без рестарта). Возвращает список активированных.

### 4. File watcher (stdlib-only)
- `runtime/hot_reload.py`: `FileWatcher` (os.stat polling) + `HotReloadService`.
  Следит за `config.json` и `plugins/`. При изменении config →
  `ConfigService.reload` + `config.changed`; при изменении plugins →
  `registry.reload_manifests()` + `manifest.reloaded`. Оба публикуют
  `kernel.lifecycle` (LAW K3 — Kernel не меняется).

### 5. Архитектурные ограничения соблюдены
- **LAW K8**: `runtime/hot_reload.py` импортирует только `contracts` + `runtime`
  + stdlib. `watchdog` НЕ используется (arch-gate clean).
- **LAW K3**: Hot Reload — runtime-событие, Kernel видит как `kernel.lifecycle`.
  Kernel НЕ модифицирован (проверено: `kernel/kernel.py` не трогал).
- `ComponentController` расширен `swap()`, не `restart()` (как требовала спецa).

## Side-effect fix (Phase 4 rename fallout)
- `runtime/runtime_host.py`, `metrics_service.py`, `snapshot_service.py` читали
  старое `proc.status` (ProcessStatus API). После Phase 4 rename → `ProcessState`
  с `.state`. Исправлено на `getattr(proc, "state", ...)`. `runtime_host.py:60`
  сломал smoke `services` mode — починен. `ProcessStatus` оставлен как alias.

## Какие файлы изменены

Созданы:
- `runtime/hot_reload.py` (FileWatcher + HotReloadService)
- `tests/test_phase5_hot_reload.py` (DoD: 5 тестов)

Изменены:
- `contracts/i_process.py` (+`swap` в IComponentController)
- `runtime/component_registry.py` (+`swap`, +`reload_manifests`)
- `runtime/services/config_service.py` (+`start_watching`/os.stat polling)
- `runtime/__init__.py` (export hot_reload)
- `runtime/kernel_runtime.py` (build_services получает plugins_dir; HotReloadService стартует)
- `bootstrap_v2.py` (+`ComponentController.swap`, +HotReloadService в build_services)
- `runtime/runtime_host.py`, `metrics_service.py`, `snapshot_service.py` (ProcessState `.state` fix)

Не изменены (LAW K3): `kernel/kernel.py`, `services/agent_platform.py` и платформы.

## Тесты (DoD)

`tests/test_phase5_hot_reload.py` — 5 тестов:
- Config hot-reload: config.json changed → reload + `config.changed` published ✅
- `ComponentController.swap()` → instance replaced, RUNNING, no Kernel.stop ✅
- Manifest reload → NEW plugin activated without restart ✅
- FileWatcher stdlib os.stat polling only (no third-party) ✅
- LAW K8: `runtime/hot_reload` imports only contracts/runtime (+stdlib) ✅

## Результаты

```
pytest tests/test_phase5_hot_reload.py -> 5 passed
pytest tests/test_architecture.py      -> 3 passed  (arch-gate GREEN, LAW K8 holds)
pytest tests/                          -> 755 passed, 15 skipped, 6 pre-existing failures
```
6 pre-existing failures — untracked graph/semantic (до сеанса, Track L/Phase 6).
Phase 5 НЕ добавил новых падений (750→755, +5 от новых тестов Phase 5).

Ad-hoc verifier (tmp, удалён): 8/8 — ConfigService hot-reload, swap no stop,
manifest reload, FileWatcher stdlib, LAW K8 clean, HotReloadService в build_services,
arch-gate green.

Smoke: `python -m runtime --mode=services` → **7 runtime services started**
(Logging, Metrics, Config, Snapshot, Supervisor, Health, HotReload). Без FAILED.

## Обновлённые ADR

- **ADR-020** (accepted): Phase 5 доказал — Hot Reload работает как runtime-событие
  без модификации Kernel (LAW K3). Config + manifest live-reload, component swap.
  File watcher stdlib-only (arch-gate сохранён). Вариант б подтверждён.

## Риски

1. Pre-existing 6 failures в untracked graph/semantic — Track L (Legacy Cleanup).
2. Hot Reload в `services` mode использует `comp_registry` (отдельный от Phase 2/3).
   В продакшене HotReloadService должен наблюдать ТОТ ЖЕ registry, что активировал
   компоненты (кандидат на Phase 7 dashboard wiring).
3. `swap()`/`reload_manifests()` вызывают `InstanceBuilder` — если builder упал,
   instance=None, Process стартует с None (деградированный). Обработка ошибок
   builder'а — зона ответственности composition root (bootstrap_v2).

## Следующий этап

Phases 1–5 закрыты. Дальше по плану:
- **Phase 6 — Legacy Cleanup** (параллельный трек): удалить `agent_service.py`,
  `graph_query_engine.py`, `stubs/`, 6 untracked тестов → снять 6 pre-existing failures.
- **Phase 7 — Live Observability Dashboard**: объединить MetricsService +
  SnapshotService + Supervisor в единый read-model; HotReloadService наблюдает
  реальный registry.
- Или **Phase 8 — Distributed Runtime**: multi-node Kernel mesh (если нужно).
