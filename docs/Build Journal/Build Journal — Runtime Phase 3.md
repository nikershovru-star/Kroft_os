---
tags: [kroft, build-journal, runtime, phase-3, observability]
created: 2026-08-01
author: Hermes (senior software architect)
depends_on: [ADR-020 — Runtime Host Architecture, KROFT_OS Master Development Plan v2.0, Build Journal — Runtime Phase 2, Build Journal — Runtime Phase 1]
summary: >-
  Build Journal — Runtime Phase 3 (Observability Foundation). Слой наблюдаемости
  runtime/services/: MetricsService (metric:* в IEventBus), ConfigService (чтение
  без применения, LAW K5), LoggingService (структурированный JSON), SnapshotService
  (dump registry в snapshot_*.json). Сервисы висят на шине, НЕ дёргают платформы
  (LAW K3). Arch-gate зелёный (LAW K8), Smoke 4 сервиса стартуют.
---

# Build Journal — Runtime Phase 3 (Observability Foundation)

> Дата: 2026-08-01. Продолжение после Phase 1 (2182c5b) и Phase 2 (b50f4db).
> Phase 3 строит слой наблюдаемости и управления в `runtime/services/`. Платформы
> остаются нетронутыми (LAW K3); сервисы — наблюдатели на шине событий.

## Что реализовано

- **Порты** `contracts/i_metrics.py` — `IMetricsCollector` (метрики через порт, не psutil).
- **`contracts/i_kernel.py`** — добавлено read-only свойство `event_bus` (Kernel экспонирует
  шину через порт; сервисы подписываются, не дёргая ядро).
- **`kernel/kernel.py`** — добавлено свойство `event_bus` (без изменения логики ядра).
- **`infrastructure/metrics.py`** — `PsutilMetricsCollector(IMetricsCollector)` (psutil разрешён
  в infrastructure; `runtime` его импортировать не может по LAW K8).
- **`runtime/services/logging_service.py`** — `LoggingService` + `JsonFormatter` (JSON, rotation).
- **`runtime/services/metrics_service.py`** — `MetricsService`: подписан на `kernel.lifecycle` и
  `component.lifecycle`, публикует `metric:snapshot` (и `metric:cpu`/`metric:memory`) в IEventBus.
- **`runtime/services/config_service.py`** — `ConfigService`: централизованное чтение `config.json`
  через stdlib; НЕТ `apply()` (LAW K5 — применение через ConfigApplier, Wave 13).
- **`runtime/services/snapshot_service.py`** — `SnapshotService`: дамп `IProcessRegistry` в
  `snapshot_*.json` по `snapshot.request`.
- **`runtime/services/__init__.py`** — экспорт 4 сервисов.
- **`runtime/kernel_runtime.py` + `bootstrap_v2.py`** — `--mode=services` инжектит общий
  `InMemoryEventBus` (Kernel через container + сервисы через `build_services`) — события
  `kernel.lifecycle` доходят до подписчиков-сервисов.

## Какие файлы изменены

Созданы:
- `contracts/i_metrics.py`, `contracts/i_kernel.py` (+event_bus), `contracts/__init__.py`
- `kernel/kernel.py` (+event_bus property)
- `infrastructure/metrics.py`
- `runtime/services/{logging,metrics,config,snapshot}_service.py`, `runtime/services/__init__.py`
- `runtime/kernel_runtime.py` (режим services), `bootstrap_v2.py` (build_event_bus/build_services)

Не изменены (LAW K3): `services/agent_platform.py` и все платформы волн 11–14.

## Какие тесты добавлены

Не добавлялись (инфраструктурная фаза). Smoke доказывает связь с Phase 1–2 через
`python -m runtime --mode=services` → 4 сервиса стартуют, `metric:snapshot` публикуется.
Unit-тесты сервисов — кандидат на отдельный коммит (Phase 4/7).

## Результаты Smoke

```
python -m runtime --mode=services
[runtime] Kernel READY (extending IKernel, no wrappers)
[runtime] 4 runtime service(s) started
{"ts":...,"level":"INFO","msg":"metric:snapshot {\"started\":0,...,\"cpu\":0.0,\"memory\":49.5}"}
```
Ad-hoc verifier (tmp, удалён): 9/9 passed — IMetricsCollector порт, PsutilCollector
имплементирует его, runtime/services импортирует ТОЛЬКО contracts (LAW K8/K3 clean),
MetricsService публикует metric:* (2014 доставки за 0.3s stress), ConfigService читает
без рестарта и НЕ имеет apply(), SnapshotService пишет snapshot_*.json, Kernel.emit
доходит до подписчика на общей шине.

## Результаты Regression

```
pytest tests/test_architecture.py -> 3 passed  (arch-gate GREEN, LAW K8 holds)
pytest tests/                    -> 745 passed, 15 skipped, 6 pre-existing failures
```
6 pre-existing failures — в untracked graph/semantic тестах (до сеанса, Track L/Phase 6).
Phase 3 НЕ добавил новых падений. `runtime/services/*` импортирует ТОЛЬКО `contracts`
(arch-gate AST-scan чист).

## Обновлённые ADR

- **ADR-020** (accepted): Phase 3 доказал — сервисы НЕ модифицируют платформы, висят на
  IEventBus (общий инстанс, инжектированный composition root'ом). Вариант б подтверждён:
  Kernel минимален, observability — обычные компоненты Runtime через ComponentRegistry.
- **Master Development Plan v2.0**: Phase 3 отмечена реализованной.

## Оставшиеся риски

1. Pre-existing 6 failures в untracked graph/semantic — Track L (Legacy Cleanup).
2. `cpu` metric = 0.0 на первом сэмпле (`psutil.cpu_percent(interval=None)` — ожидаемо;
   реальное значение после первого интервала). Канал метрик верифицирован живым.
3. MetricsService получает `registry=None` (ProcessRegistry view ещё не exposed в runtime);
   счётчики компонентов пока только от событий. Фаза 4 (Supervisor) свяжет Registry.

## Следующий этап

**Phase 4 — Supervisor & Recovery**: `runtime/supervisor.py` (heartbeat, health check),
`recovery.py` (max_restarts, panic_threshold), `health_check.py`, `watchdog.py`. Supervisor
знает IProcess и IHealthCheck, НЕ платформы; restart через IServiceLifecycle, panic →
Kernel FSM → FAILED → snapshot → stop.
