# H0 RESULT — HERMES ↔ KROFT COGNITIVE BRIDGE (READ-ONLY)

**Статус:** DONE (с честным GAP по resolve), verified against repo 2026-08-16
**ТЗ:** H0 — HERMES ↔ KROFT COGNITIVE BRIDGE 0
**Следующий шаг:** НЕ начат (ТЗ §27: отдельное GO на H1/Federation Envelope)

## Hermes tool architecture

Hermes Agent (этот чат) — внешний исполнительный агент. Bridge вызывается
Hermes как обычный Python-модуль (`bridges/kroft_bridge.py`) через terminal/
execute_code. Hermes НЕ импортирует внутренности KROFT — только публичный
`KroftBridge` API.

## KROFT entrypoints (forensic, Step 2)

| Entrypoint | Где | Reuse для bridge |
|---|---|---|
| `KroftApp` (run_kroft.py) | composition root | ✅ bridge грузит его (read-only config) |
| `ReferenceSearchService` (KroftApp.search) | kernel/search.py | ✅ kroft_search / kroft_query |
| `GraphQueryEngine` | services/graph_query_engine.py | ⚠️ живёт ТОЛЬКО в cli/ DI-container, НЕ в KroftApp |
| `cli/commands.py` cmd_status/search/query/semantic/hybrid | CLI | ❌ требуют Kernel+container+config, НЕ reuse (bridge грузит KroftApp напрямую) |
| `ReferenceKnowledgeResolution` | services/knowledge_resolution.py (ADR-028 Этап 1) | ⚠️ требует IGraphQuery, НЕ выставлен в KroftApp |

## Existing reusable APIs (Step 3 — не дублировали)

| Требование | Существует | Reuse | Новый код |
|---|---|---|---|
| status | KroftApp.graph/memory/trust/config | ✅ | — |
| search | ReferenceSearchService.search_hybrid | ✅ | — |
| semantic | KroftApp.embedding_adapter | ✅ (если wiring) | — |
| hybrid | ReferenceSearchService | ✅ | — |
| query | ReferenceSearchService (lexical) | ✅ | — |
| resolution | ReferenceKnowledgeResolution + ResolutionLevel | ⚠️ GAP (нет IGraphQuery в KroftApp) | — |
| audit | KroftApp subgraph/memory/federation/persistence атрибуты | ✅ | — |

## Bridge (Step 4)

`bridges/kroft_bridge.py` (НОВЫЙ файл, вне kernel/contracts/services/adapters):
- `KroftBridge` — lazy boot `KroftApp` (agent_runtime=False, federation=False,
  embedding="none", llm="none", run_demo=False) — READ ONLY, LOCAL ONLY (in-process).
- `KroftToolResult` — structured DTO (ok/operation/result/metadata/provenance/errors).
- `KroftBridge.status/search/query/resolve/audit` + module-level `kroft_status/...`.
- Импорты: ТОЛЬКО `contracts` (ResolutionLevel) + `composition.run_kroft.KroftApp`.
  KROFT НЕ импортирует Hermes (ТЗ §15). Bridge — единственная граница (ТЗ §16).
- READ-ONLY гарантия (ТЗ §23): НЕТ методов ingest/save/persist/merge/commit.
  Тест `test_read_only_guarantee` доказывает отсутствие write-API.
- Graceful degradation (ТЗ §14): KROFT недоступен → `ok=False, error=...`,
  НЕ «ничего не найдено».

## New code

- `bridges/kroft_bridge.py` (~290 строк, K1-чистый: contracts + composition root)
- `tests/bridge/test_kroft_bridge.py` (10 тестов, mocks/fakes, НЕ prod snapshot)

## Tests

`tests/bridge/test_kroft_bridge.py` — 10 passed:
status / search / query / resolve / resolve_gap / resolve_unknown_level /
audit (4 targets) / unavailable / read_only_guarantee / independent_from_hermes.

Smoke (ad-hoc, удалён): реальный `KroftBridge()` → реальный `KroftApp`
(без snapshot) → status/search/audit работают; resolve → честный GAP.

## Regression

Мои файлы ИЗОЛИРОВАННО зелёные:
- bridge 10/10
- architecture gate 27/27
- ADR-028: knowledge_resolution 7/7, memory_evolution_sidecar 4/4,
  reflection_cosmic 4/4, self_evolution_cycle 11/11, memory_evolution 10/10,
  reflection_engine 11/11

ШИРОКАЯ комбинация (pytest tests/ целиком) показывает 2 F — НЕ воспроизводятся
при изолированном прогоне моих файлов. Причина: sibling diff из ДРУГИХ окон
(git status: contracts/i_orchestrator.py, i_workflow.py, kernel/search.py и др.
модифицированы другими агентами) + возможный test-ordering pollution.
По ТЗ §2 (STOP на неожиданный sibling diff) — РЕПОРТ, НЕ PATCH.

## Security (ТЗ §17)

- LOCAL ONLY: in-process import KroftApp, НЕТ TCP listener / network endpoint.
- READ ONLY: bridge НЕ пишет knowledge/graph/memory/snapshot/federation/code.
- Federation write-path НЕ доступен (federation=False в boot-config).

## Remaining gaps (честно, ТЗ §27)

1. **kroft_resolve → GAP.** `ReferenceKnowledgeResolution` (ADR-028 Этап 1)
   требует `IGraphQuery`, который `KroftApp` read-only boot НЕ выставляет
   (GraphQueryEngine живёт только в `cli/` DI-container). Bridge возвращает
   `ok=False` + честное сообщение GAP, НЕ симулирует resolve.
   → Закрывается в H1 (нужен wiring GraphQueryEngine в KroftApp ИЛИ
     передача IGraphQuery в bridge; меняет composition root, НЕ kernel).
2. **kroft_query** использует `ReferenceSearchService` (lexical/hybrid), НЕ
   семантическую абстенцию (`query_with_abstention` — только в cli/ container).
   Для READ-ONLY H0 этого достаточно; семантика — в H1.

## Acceptance (ТЗ §25)

- Architecture: Hermes → Bridge → existing KROFT ✅ (доказано кодом)
- Functional: status ✅ / search ✅ / query ✅ / audit ✅ работают;
  resolve → честный GAP (не fake) ✅
- Isolation: KROFT не знает о Hermes ✅ (bridge K1-чист, нет `from hermes`)
- Safety: H0 = READ ONLY ✅ (тест доказывает)
- Regression: мои файлы зелёные ✅ (широкая комбинация — sibling diff, см. выше)
- Hermes реально может вызвать kroft_status + kroft_search ✅ (smoke доказан)

## STOP — ждём GO на H1

По ТЗ §27 НЕ переходим к Federation Envelope / KnowledgeEnvelope автоматически.
Следующий шаг (отдельный GO): H1 — KROFT KnowledgeEnvelope поверх существующей
федерации (identity / trust gate / can_accept / quarantine / replay / CRDT /
multi-hop), закрывая GAP #1 выше.
