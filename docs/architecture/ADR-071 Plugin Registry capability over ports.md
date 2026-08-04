---
id: ADR-071
title: "Plugin Registry — deterministic capability registry over existing ports (ТЗ-PLUGIN-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [plugin, registry, extensibility, determinism, LLM-free, I-09, K1, K6, K8, O1]
---

# ADR-071 — Plugin Registry: deterministic capability registry (ТЗ-PLUGIN-01)

## Context
SEARCH/RESEARCH дали извлечение и синтез. PLUGIN-01 даёт РАСШИРЯЕМОСТЬ: внешние capabilities
регистрируются как плагины за портом, discoverable и invocable детерминированно, без хардкода.
База для TZ-029/TZ-017. Standalone (Флаг C), НЕ в build_kernel. LLM-free (I-09). O1: плагины
read-only w.r.t. HARD/FSM/контрактов.

K5-разведка (commit 0) нашла: `IPlugin` (CLI/export/crawl hooks, Stage 25) УЖЕ существует в
`contracts/plugin.py`. Создавать второй `IPlugin` в `i_plugin.py` = дублирование границы
(запрещено). Но `IPluginRegistry`/`PluginManifest`/`PluginResult`/`invoke` НЕ существовали.
`ICapabilityRegistry` (runtime/capability_registry.py) есть, но это реестр именованных
capabilities (register(name, any)), НЕ plugin-реестр с invoke/Manifest.

## Decision
Расширить `contracts/plugin.py` (НЕ создавать `i_plugin.py`):
- `ICapabilityPlugin` — новый invoke-capable под-порт (id/name/capabilities/invoke). Отделён от
  CLI `IPlugin` (one-port-per-boundary: capability-plugin registry ≠ CLI-plugin-loading).
- `IPluginRegistry` — register/unregister/list/get/has/invoke.
- `PluginManifest` / `PluginResult` — frozen VO с реальными типами (урок Флага 1 LLM-01).
- `PluginInvocationError` — для duplicate/invoke-failure.
- `IPlugin` (CLI) НЕ тронут -> существующий `test_plugins.py` (10 тестов) остаётся зелёным.

`ReferencePluginRegistry` (kernel/plugin.py) — in-memory deterministic реестр. Reference-плагины
`SearchPlugin`/`ResearchPlugin` ОБЁРТЫВАЮТ существующие порты `ISearchService`/`IResearchService`
(К5: переиспользование, НЕ дублирование). `build_plugin_registry` — отдельная standalone фабрика.

Обязательные ограничения (reviewer flags SEARCH/RESEARCH + ТЗ):
- **Флаг C** — НЕ в `build_kernel`; standalone фабрика; ядро не зависит от registry (K6), god-factory
  (Флаг 1 OBS-01) не усугубляется.
- **I-09 (determinism)** — list() сортирован по id (стабильный порядок); invoke детерминирован.
- **O1 (read-only)** — reference-плагины ТОЛЬКО читают (search/research); НЕ мутируют HARD/FSM/
  контракты; registry НЕ мутирует плагины.
- **K8 (negative)** — unknown-id invoke -> PluginResult(ok=False, error); duplicate register ->
  PluginInvocationError; unregister unknown -> no-op.

## Consequences
- ✅ Единый детерминированный plugin-реестр поверх существующих портов без их дублирования.
- ✅ K1: contracts + stdlib only (порт); kernel/plugin.py импортирует только contracts.
- ✅ K6: ядро не импортирует plugin-реестр; интеграция через standalone фабрику.
- ✅ K8: negative gate-тесты (unknown id / duplicate / bad args / unregister-unknown).
- ✅ O1: read-only reference-плагины доказаны тестом (research без writeback не растит память).
- ⚠️ Non-scope: реальный marketplace / загрузка кода извне / sandboxing — только in-memory
  реестр предзарегистрированных reference-плагинов (безопасность загрузки — future).

## Alternatives considered
- Создать `contracts/i_plugin.py` с новым `IPlugin` -> ОТВЕРГНУТО: дублировало бы существующий
  CLI `IPlugin` (K5/one-port-per-boundary). Введён `ICapabilityPlugin` вместо этого.
- Добавить `invoke` в существующий `IPlugin` -> ОТВЕРГНУТО: сломало бы abstractmethod-контракт
  и `test_plugins.py`.

## Evidence
- `tests/test_plugin_registry.py`: 14 K8 тестов (register/list/get, invoke->PluginResult,
  determinism, unregister, duplicate->error, unknown->error, O1 read-only, composition, factory).
- Smoke: list=['research','search']; search invoke -> 2 hits; research invoke -> summary;
  determinism True; unknown id -> ok=False; duplicate -> PluginInvocationError.
- `tests/test_plugins.py` (CLI IPlugin): 10 passed (не сломан).
- Full suite GREEN, gate 14/14, akb-lint PASSED.
