---
tags: [kroft, adr, bootstrap, runtime, architecture]
created: 2026-07-31
status: in_progress
version: 1.1
updated: 2026-07-31
author: Hermes (senior software architect)
depends_on: []
superseded_by: ADR-019
related: [Bootstrap Initiative v2 — Master Roadmap]
summary: >-
  Bootstrap Initiative — Phase A (Composition Root) ГОТОВА. Инициатива НЕ
  закрыта: дальше — ADR-019 (Kernel Runtime Architecture) + Bootstrap Initiative
  v2 Master Roadmap (фазы B–L с DoD/Guardrails/Smoke).
---

# ADR-018 — KROFT_OS Bootstrap & Runtime Lifecycle

> **Статус: `in_progress` (только Phase A — Composition Root).** Инициатива НЕ
> закрыта. Дальнейшее развитие ядра вынесено в **ADR-019 (Kernel Runtime
> Architecture)** — контракт `KernelRuntime`/`IServiceLifecycle`/`IProcessRegistry`/
> `EventLoop`/Scheduler/Supervisor. Phase A сделала `bootstrap.py` единым входом;
> но `bootstrap.py` собирает контейнер и вызывает агента один раз — это CLI,
> не OS. Непрерывный Runtime появляется в Phase B (см. ADR-019).

## Контекст

После закрытия 14 волн выяснилось, что платформы волн 11–14 (`AgentPlatform`,
`Router`, `OmniRouteAdapter`, `WorkflowPlatform`) существуют как независимые
модули **без сквозной сборки**. Legacy `main.py` — запускаемый entrypoint, но
стоит на старых сервисах (`VaultStreamCrawler`, `GraphQueryEngine`,
`AgentService` rule-based) и вообще не знает про волны 11–14. Результат: ОС
«готова» как библиотека платформ, но **не запускается как единое целое**.

Дополнительно: без живого model backend (OmniRoute @:20128) ядро вообще не
могло бы ответить. Требование пользователя: *отсутствие внешнего backend не
должно мешать загрузке ядра* → нужен обязательный офлайн-fallback LLM.

## Решение

1. **`adapters/mock_llm_adapter.py` — `MockLlmAdapter`** (обязательный fallback).
   Реализует `ILlm` + `IModelMetadata` + `IHealth`. Детерминированный ответ,
   `ping() → True` всегда. Нулевая сеть. Drop-in замена `OmniRouteAdapter` на
   уровне порта.

2. **`bootstrap.py` — единый Composition Root** (новый entrypoint = новый main).
   Диаграмма загрузки (per spec):

   ```
   python bootstrap.py
           │
           ▼
   Load Config            (JSON/YAML, мерж над DEFAULT_CONFIG)
           │
           ▼
   Build DI Container     (infrastructure.DependencyContainer)
           │
           ▼
   Init Platforms
    ├─ AgentPlatform
    ├─ WorkflowPlatform   (build_executor: Reflection + RetryManager)
    ├─ MemoryPlatform     (Wave 9)
    ├─ KnowledgePlatform  (Wave 8)
    ├─ LearningPlatform   (InMemoryLearningStore, Wave 12)
    ├─ OptimizationPlatform (PatternBasedOptimizer, Wave 13)
    └─ EventBus           (InMemoryEventBus)
           │
           ▼
   LLM Factory
    ├─ OmniRouteAdapter   (если :20128 доступен, ping()==True)
    └─ MockAdapter        (ОБЯЗАТЕЛЬНЫЙ fallback)
           │
           ▼
   Router                 (adapters.router.Router(policy_engine, {provider: llm}))
           │
           ▼
   Runtime (start/stop)   печатает S1-логи, держит агента + legacy-сервисы
   ```

3. **`AgentPlatform.ask(goal) -> str`** — добавлен в `IAgentPlatform` (abstract)
   и реализован как thin wrapper над `run()`, извлекает ответ последнего шага.
   Позволяет `agent.ask("Hello")` (spec S2).

4. **S4 — Legacy VaultCrawler как сервис платформы.** `Runtime._register_legacy_services`
   монтирует `VaultStreamCrawler` внутрь контейнера (`IFileSystem` + `IGraphBuilder`
   + `IEventBus` + `vault_path`), НЕ переписывая его и НЕ запуская отдельно.
   Если legacy-адаптеры недоступны — тихий skip (degraded mode), загрузка
   продолжается.

## Границы (честно)

- **Что НЕ сделано:** bootstrap НЕ переписывает legacy-сервисы (`GraphQueryEngine`,
  `AgentService`, `DesktopService`). Миграция — по одному модулю (per spec),
  это отдельная работа. Сейчас legacy-код живёт параллельно; `bootstrap.py`
  поднимает платформы волн 11–14, `main.py` остаётся legacy-входом.
- **`PolicyEngine` опционален** на загрузке: если недоступен, `Router` получает
  `engine=None` и корректно работает в no-policy режиме (adapter вызывается
  напрямую). В текущем прогоне PolicyEngine доступен (через `ModelRegistry.register_source`).
- **MockLlmAdapter — fallback, не замена.** При поднятом OmniRoute (`--llm omniroute`
  и :20128 up) Runtime использует реальную модель; Mock остаётся в карте адаптеров
  Router-а как запасной вход.

## Smoke-контракт (проверен ad-hoc, 14/14)

- **S1** `python bootstrap.py` → `Kernel started` / `Platforms initialized` /
  `Router initialized` / `LLM initialized (Mock)` / `Runtime ready`.
- **S2** `agent.ask("Hello")` → ответ через MockAdapter (`[mock:mock-local] ack: ...`).
- **S3** `:20128` down → `OmniRoute unreachable, using fallback`; Runtime продолжает.
- **S4** `--vault <path>` → `Legacy VaultCrawler registered as platform service`.

## Последствия

- Арх-гейт: **не нарушен** (bootstrap.py — composition root, ему разрешён импорт
  adapters/services; `test_no_forbidden_cross_layer_imports` и
  `test_services_do_not_cross_import` зелёные).
- Регресс волн 5–14: **222 passed / 10 skipped**.
- `legacy main.py` НЕ удалён — пользователь явно сказал «постепенно переводить
  старые сервисы», не переписывать всё сразу.
