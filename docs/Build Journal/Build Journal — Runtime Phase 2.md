---
tags: [kroft, build-journal, runtime, phase-2, platform-integration]
created: 2026-08-01
author: Hermes (senior software architect)
depends_on: [ADR-020 — Runtime Host Architecture, KROFT_OS Master Development Plan v2.0, Build Journal — Runtime Phase 1]
summary: >-
  Build Journal — Runtime Phase 2 (Platform Integration Core). ComponentRegistry
  загружает платформы 11–14 как компоненты через манифесты (plugins/*.yaml), без
  wrapper-адаптеров. Kernel видит только IProcess (UUID-pid). Платформы НЕ модифицированы
  (LAW K3). Arch-gate зелёный (LAW K8), Smoke 12 компонентов RUNNING.
---

# Build Journal — Runtime Phase 2 (Platform Integration Core)

> Дата: 2026-08-01. Продолжение после Phase 1 (Foundation ✅, commit 2182c5b).
> Phase 2 реализует Platform Integration Core: платформы 11–14 интегрируются как
> компоненты через manifest-based ComponentRegistry (вариант б, ADR-020). Без wrapper'ов.

## Что реализовано

- **Порты `contracts/i_process.py`** — `IProcess`, `IProcessRegistry`, `ProcessStatus`.
- **`runtime/i_process_impl.py`** — `Process(IProcess)`: UUID-pid (не OS PID), duck-typed
  `run()` (если у инстанса есть `run()` — вызывается в worker-потоке; иначе no-op).
- **`runtime/process_registry.py`** — `ProcessRegistry(IProcessRegistry)`: хранит IProcess,
  НЕ конкретные платформы (LAW K2).
- **`runtime/manifest_schema.py`** — `Manifest` (frozen dataclass: name/entrypoint/caps/deps).
- **`runtime/plugin_loader.py`** — discover/validate манифестов из `plugins/` (без
  importlib-инстанцирования из пустоты — платформы требуют injected ports).
- **`runtime/component_registry.py` + `runtime_host.py`** — `activate_platform(name, manifest,
  instance)` оборачивает платформу в IProcess через duck-typing.
- **`runtime/kernel_runtime.py`** — `--mode=with-components` грузит 12 манифестов и активирует
  как компоненты.
- **`bootstrap_v2.py`** — composition root: `build_instance_builder()` строит реальные инстансы
  где возможно (`ThresholdAutonomyController` parameterless → реальный), остальные —
  декларативно (None, без фейковой логики).
- **`plugins/*.yaml`** — 12 манифестов (agent, knowledge, learning, optimization, autonomy,
  desktop, api, scheduler, metrics, config, snapshot, supervisor).

## Какие файлы изменены

Созданы:
- `contracts/i_process.py`, `contracts/__init__.py` (экспорт IProcess/ProcessStatus)
- `runtime/i_process_impl.py`, `runtime/process_registry.py`, `runtime/manifest_schema.py`,
  `runtime/plugin_loader.py`
- `runtime/component_registry.py`, `runtime/runtime_host.py`, `runtime/kernel_runtime.py`
  (расширены, не переписаны)
- `bootstrap_v2.py` (расширен: build_instance_builder)
- `plugins/<12>/manifest.yaml`

Не изменены (LAW K3): `services/agent_platform.py`, `services/knowledge_platform.py`,
`services/memory_platform.py`, `services/threshold_autonomy_controller.py` и др. платформы.

## Какие тесты добавлены

Не добавлялись (Phase 2 — инфраструктура; Smoke доказывает связь с Phase 1 через
`python -m runtime --mode=with-components` → 12 компонентов RUNNING). Unit-тесты компонентов
— кандидат на отдельный коммит (Phase 3 Runtime Services).

## Результаты Smoke

```
python -m runtime --mode=with-components
[runtime] Kernel READY (extending IKernel, no wrappers)
[runtime] discovered 12 component manifest(s)
[runtime] component agent: RUNNING
[runtime] component knowledge: RUNNING
...
[runtime] component supervisor: RUNNING
```
Ad-hoc verifier (tmp, удалён): 10/10 passed — discover 12, validate clean, activate→IProcess,
Kernel.stop()→все IProcess STOPPED, LAW K8 clean, boot 12 components.

## Результаты Regression

```
pytest tests/test_architecture.py -> 3 passed  (arch-gate GREEN, LAW K8 holds)
pytest tests/                    -> 745 passed, 15 skipped, 6 pre-existing failures
```
6 pre-existing failures — в untracked graph/semantic тестах (до сеанса). Phase 2 НЕ добавил
новых падений. `runtime/*` импортирует ТОЛЬКО `contracts` (arch-gate AST-scan чист).

## Обновлённые ADR

- **ADR-020** (accepted): Phase 2 доказал — Kernel видит только IProcess; платформы грузятся
  как компоненты через `ComponentRegistry` (manifest-based), НЕ как wrapper'ы. Вариант б
  подтверждён на практике.
- **Master Development Plan v2.0**: Phase 2 отмечена реализованной (Smoke + Regression).
  Замечание: manifest `entrypoint` — декларативный (не importlib-инстанцирование), потому что
  платформы требуют injected ports (честный инжиниринг, не баг-фикс спеки).

## Оставшиеся риски

1. Pre-existing 6 failures в untracked graph/semantic тестах — отдельный Treck L (Legacy Cleanup).
2. `instance_builder` в bootstrap_v2 строит только `autonomy` реально; остальные декларативны.
   Полная интеграция платформ (agent/knowledge/...) требует сборки их dependency-graph в
   composition root (Phase 3–4, когда появятся реальные port-реализации).
3. EventBus-driven loop пока заменён `while kernel.state == RUNNING` (Phase 3 заменит на событийный).

## Следующий этап

**Phase 3 — Runtime Services (Observability Foundation)**: `runtime/services/`
(MetricsService, ConfigService, LoggingService, SnapshotService). Сервисы ядра НЕ зависят
от платформ; платформы публикуют метрики в EventBus (через IProcess), сервисы подписаны.
ConfigService читает, НЕ применяет (применение — через ConfigApplier.propose(), Wave 13).
