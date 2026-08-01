---
title: "KROFT_OS — Architecture Map & Current Phase (handoff document)"
version: "1.0"
date: "2026-08-01"
purpose: >
  Самодостаточная карта архитектуры KROFT_OS для передачи другой LLM-модели.
  Содержит: что такое система, текущую структуру, на каком этапе мы находимся,
  что сделано / что осталось, ключевые законы (LAW K1-K8) и карту файлов.
  Читать ПЕРЕД любой работой с кодом.
---

# KROFT_OS — Architecture Map & Current Phase (Handoff)

> **Это живая карта для другой модели.** Не меняй законы (LAW K1-K8) и не
> ослабляй Architecture Gate без явной просьбы. См. раздел «Hard Constraints».

## 0. Что такое KROFT_OS

**KROFT_OS** (Knowledge Runtime & Orchestration Framework Technology Operating
System) — инженерная операционная система для создания, управления и эволюции
AI-агентов. Это НЕ приложение и НЕ набор скриптов — саморазвивающаяся платформа,
где знания / архитектура / код / решения связаны в единую систему.

- Архитектурный стиль: **Clean / Hexagonal** (порты и адаптеры).
- Ядро (kernel) — минимальный микроядро с lifecycle FSM.
- Вся сборка (wiring) вынесена в **Composition Root** (`composition/`).
- Документация архитектуры живёт в `docs/architecture/` (ADR-001..029, AKB).

## 1. Текущий статус — на каком этапе мы

**Phase B (Architecture Stabilization & Composition Root) — ВЫПОЛНЕНА.**
**Phase C (Policy & Domain Boundary) — ВЫПОЛНЕНА.**

| Phase | Статус | Что сделано |
|-------|--------|-------------|
| Variant A | ✅ DONE | Единый git-репозиторий (docs + code + история KnowledgeOS-v5) |
| Phase B.1 | ✅ DONE | Слой `composition/` (7 модулей), `main.py`/`bootstrap_v2.py` — thin-entrypoint |
| Phase B.2 | ✅ DONE | Kernel constructor injection (ядро ничего не создаёт) |
| Phase B.3 | ✅ DONE | `IStateRepository` порт + реализация; `SnapshotStore` убран из Kernel |
| Phase B.4 | ✅ DONE | `DependencyContainer` убран из Kernel (K1-нарушение устранено) |
| ADR-026/027/028/029 | ✅ DONE (proposed) | Composition Root, Dependency Inversion, Kernel Purity, Bootstrap Lifecycle |
| **Phase C.1** | ✅ DONE | **V3 устранён**: `estimate_cost` порт в `contracts/cost.py`; adapters→contracts (НЕ policies) |
| **Phase C.2** | ✅ DONE | `PolicyRegistry` (policies/registry.py) — политики подключаемы по имени |
| **Phase C.3** | ✅ DONE | PolicyEngine pipeline (veto→filter→rank→fallback) уже реализован (Wave 5) |
| ADR-030 | ✅ DONE (proposed) | Policy & Domain Boundary |
| **Phase D** | ⏸ NEXT (по roadmap) | Configuration & Secrets (ConfigService, Profiles, Secrets) |
| Phase E | ⏸ | MCP Gateway (unified client protocol) |
| Phase F | ⏸ | Supervisor & Recovery (checkpoint/rollback) |
| Phase G | ⏸ | Distributed Runtime (Cluster, Consensus) |

**Метрики (последний прогон):**
- Тесты: `757 passed, 19 skipped, 0 failed`
- Architecture Gate: `3 passed` (GREEN)
- **ВСЕ основные слои (kernel, runtime, services, adapters, infrastructure, policies) зависят ТОЛЬКО от `contracts`** — платформенная чистота достигнута.

## 2. Архитектурная карта (целевая, достигнута)

```
                Clients (cli/, bootstrap_v2.py)
                    │
              Composition Root  (composition/)
              build_system(): config → DI → runtime → kernel → plugins → services → ready
                    │
      ┌─────────────┴─────────────┐
      │                           │
   Runtime                    Kernel (lifecycle FSM)
      │                      imports: contracts, runtime, stdlib ONLY
      └─────────────┬─────────────┘
                    │
                Contracts (порты: IKernel, IEventBus, IStateRepository, IFileSystem, ...)
                    │
      ┌───────┬──────────┬─────────┐──────────┐
      │       │          │         │          │
 Services  Adapters  Infrastructure  Plugins   Policies
```

**Инвариант (НЕ нарушать):** Kernel не знает ничего ниже Runtime. Все
`infrastructure.*` импорты ушли из `kernel/` — это правильное состояние.

## 3. Карта файлов (что где лежит)

### `kernel/` — микроядро (ЧИСТОЕ)
- `kernel.py` — `Kernel(IKernel)`: lifecycle FSM (UNINITIALIZED→INITIALIZED→
  RUNNING→STOPPED), orchestration. Constructor injection:
  `Kernel(runtime_context, event_bus, state_repository, registry, services=None,
  container=None [DEPRECATED])`.
- Импортирует ТОЛЬКО `contracts`, `runtime`, stdlib. **НЕТ infrastructure.**

### `contracts/` — порты (abstract interfaces)
- `i_kernel.py` — `IKernel`, `LifecycleState`
- `i_state_repository.py` — `IStateRepository` (save/load_state, save/load_snapshot,
  checkpoint, rollback) — НОВЫЙ порт Phase B.3
- `i_event_bus.py`, `i_file_system.py`, `i_graph_builder.py`, `i_graph_query.py`,
  `snapshotable.py` (ISnapshotable), `i_policy.py`, `i_llm.py`, `i_memory.py`,
  `i_knowledge.py`, `i_workflow.py`, `i_agent.py`, `i_eval.py`, `i_process.py`,
  `i_metrics.py`, `model_registry.py`, ... (27 файлов)

### `composition/` — Composition Root (НОВЫЙ слой, Phase B.1)
- `container_builder.py` — `build_container(vault_path, loader, desktop_adapter)`:
  регистрирует порты + адаптеры + сервисы + `IStateRepository`. Единственная
  точка сборки.
- `kernel_factory.py` — `build_kernel()`, `build_services()`, `ComponentController`
- `runtime_factory.py` — `build_capability_registry()`
- `adapter_factory.py` — `build_core_adapters()`, `build_watcher()`, `build_server()`
- `service_factory.py` — `wire_agent()`, `wire_scheduler()` (фасады)
- `plugin_factory.py` — `build_plugin_loader()`
- `bootstrap.py` — `build_system()` / `shutdown_system()` (оркестрация ADR-029)

### `runtime/` — runtime-слой (ЧИСТЫЙ, imports only contracts)
- `context.py` — `RuntimeContext`
- `capability_registry.py`, `component_registry.py`, `kernel_runtime.py`,
  `services/` (ConfigService, LoggingService, MetricsService, SnapshotService),
  `supervisor/`, `hot_reload.py`, `recovery/`, `i_process_impl.py`, ...

### `services/` — application-слой (imports only contracts)
- `vault_stream_crawler.py`, `graph_query_engine.py`, `content_index.py`,
  `incremental_tracker.py`, `agent_service.py`, `policy_engine.py`,
  `knowledge_platform.py`, `memory_platform.py`, `workflow_*.py`,
  `reflection.py`, `retry_manager.py`, `scheduler.py`, ... (32 файла)

### `adapters/` — concrete port implementations (imports only contracts)
- `filesystem_adapter.py` (LocalFileSystemAdapter), `embedding.py`,
  `exporters/` (dot/json/gexf), `file_watcher.py`, `http_server.py`,
  `agent_adapter.py`, `desktop_adapter.py`, `model_platform.py`,
  `omni_route_adapter.py`, `router.py`, `rule_based_planner.py`, ...

### `infrastructure/` — Composition Root helpers (imports only contracts)
- `container.py` (DependencyContainer), `eventbus.py`, `graph_builder.py`,
  `config_loader.py`, `snapshot_store.py`, `state_repository.py` (StateRepository,
  impl IStateRepository), `metrics.py`, `plugin_loader.py`

### `policies/` — policy implementations (imports only contracts)
- `budget_policy.py`, `privacy_policy.py`, `security_policy.py`,
  `provider_selection_policy.py`

### `plugins/` — пустой (расширяется через PluginLoader)

### `cli/` — CLI entrypoint (Composition Root consumer)
- `parser.py`, `commands.py`, `repl.py`

### Корень
- `main.py` — thin entrypoint, делегирует в `composition.build_container`
- `bootstrap_v2.py` — runtime-host entrypoint, делегирует в `composition`
- `tests/` — pytest suite (757 tests + arch-gate)

### `docs/architecture/` — документация (ВНЕ git по Variant A)
- `ADR-001..029*.md` — решения
- `AKB/` — Architecture Knowledge Base (machine-readable YAML): `laws.yaml`
  (K1-K8), `adrs.yaml` (29 ADR), `forbidden.yaml` (F1-F6), `history.yaml`,
  `patterns/`, `tech_catalog.yaml`, `evidence_levels.yaml`, `glossary.yaml`
- `Dependency Report — Phase B.md` — полный аудит зависимостей
- `PROJECT_CONTEXT_MAP.md` — архитектурный паспорт (v1.1 на диске)

## 4. Hard Constraints (НЕ нарушать без явной просьбы)

1. **LAW K1** — Kernel imports ONLY `contracts/` + `runtime/`. Никогда не
   импортируй `services/`, `adapters/`, `infrastructure/` из `kernel/`.
2. **LAW K3** — Wiring (создание/связывание) только в `composition/`.
3. **LAW K5** — Humans Approve: не push без разрешения, не меняй законы вслепую.
4. **LAW K6** — Межслойное общение ТОЛЬКО через `contracts/` порты.
   `adapters` → ТОЛЬКО `contracts` (НЕ `policies`/`services`/`infra`).
   `policies` → ТОЛЬКО `contracts`. `services` → `contracts` (+`policies`).
   Проверяется гейтом: `policies` в `PROJECT_PKGS`, `ALLOWED["adapters"]={contracts}`.
5. **Architecture Gate** — `tests/test_architecture.py` НЕ ослаблять. Если он
   падает — код нарушает K1/K6, чинить код, не гейт.
6. **Никакого `git add -A`** — только поименованные пути.
7. **Без авто-резолва конфликтов** — остановись и покажи пользователю.

## 5. Что сделано в Phase B (детали для контекста)

- `kernel.py` больше НЕ импортирует `infrastructure`. K1-нарушение (V1/V2) устранено.
- `IStateRepository` (contracts) заменяет узкий `SnapshotStore`: добавлены
  `checkpoint(label)` / `rollback(label)` — готовность к Recovery Engine.
- `composition/bootstrap.build_system()` реализует жизненный цикл ADR-029.
- Legacy `Kernel(container=...)` оставлен (deprecated) для обратной совместимости
  тестов — кандидат на удаление.

## 6. Что делать дальше (Phase D и крупные этапы)

**Phase D (следующий, по roadmap):** Configuration & Secrets.
- `Config/` с `config.yaml`, `secrets.yaml`, `profiles/{dev,prod,local}.yaml`
- Единый `ConfigService.load_profile("local")` с `config.llm.provider`,
  `config.paths.vault`, `config.desktop.adapter`
- Environment isolation, Secrets abstraction

**Phase E:** MCP Gateway (unified client protocol, session mgmt, tool routing,
streaming) — реальная ценность пользователю.

**Крупные этапы (готовы к реализации поверх Phase B/C):**
- Supervisor & Recovery (через `IStateRepository.checkpoint/rollback`)
- Multi-Agent Runtime
- Plugin Marketplace
- Distributed Runtime / Cluster Mode (Phase G)
- Self-Healing Kernel

## 7. Как проверить состояние (команды)

```bash
cd KROFT_OS
python -m pytest tests/ -q            # ожидаем: 757 passed, 19 skipped, 0 failed
python -m pytest tests/test_architecture.py -q   # ожидаем: 3 passed (GREEN)
python -c "import kernel,runtime,services,contracts,composition,policies"  # imports OK
grep -rnE "import infrastructure|from infrastructure" kernel/     # должно быть пусто (K1)
grep -rnE "from policies|import policies" adapters/     # должно быть пусто (K6/V3)
```

## 8. История коммитов (последние, Phase B/C)

```
cab5ebb docs(phase-c): ADR-030 Policy Boundary + AKB update
6f0f2ca feat(policies): Phase C.2 — PolicyRegistry (pluggable by name)
3a899c6 fix(arch): Phase C.1 — resolve V3 (adapters->policies)
bd7bba3 docs(phase-b): ADR-029 Bootstrap Lifecycle + AKB update
1bd9140 refactor(kernel): B.2/B.3/B.4 — constructor injection, drop infrastructure
4362a62 feat(composition): Phase B.1 — Composition Root layer (7 modules)
a65eb30 feat(contracts): IStateRepository port + infrastructure impl
```

---
*Сгенерировано Hermes (Architecture Intelligence Protocol) как handoff-карта.
Актуально на 2026-08-01. Для свежей сверки см. `git log` + `docs/architecture/AKB/`.*
