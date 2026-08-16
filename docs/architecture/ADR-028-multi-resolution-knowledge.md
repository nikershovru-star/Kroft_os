# ADR-028 — Multi-Resolution Knowledge (LOD) для KROFT_OS

**Статус:** принято (verified against repo, 2026-08-16)
**Автор:** Никита (через Hermes + claude.ai artifact)
**Связь:** метафора масштабов (видео «Размеры планет и вселенная») → двухосевая модель → forensic-audit → этот ADR.

## Контекст

Первоначальный план исходил из того, что Causal Analyzer, Hypothesis Engine, Capability Manager, Knowledge Boundary и Federation — новые модули. **READ-ONLY аудит репозитория доказал обратное: все они УЖЕ существуют.** Реализация плана «как есть» создала бы второй путь рядом с работающим — нарушение K2/K5.

Единственный реальный GAP после аудита: **система не умеет менять разрешение (LOD) собственного знания** и **не держит provenance при сжатии**. Это и есть ось, которую нащупала метафора масштабов.

## Что реально есть (проверено чтением файлов)

| Возможность | Статус | Где |
|---|---|---|
| Causal Analyzer | ЕСТЬ | `kernel/causal_analyzer.py` |
| Hypothesis / Capability / Experiment / Self-Evaluator | ЕСТЬ | `contracts/i_self_evolution_cycle.py` |
| Knowledge Boundary (эпистемическая) | ЕСТЬ, УЗКАЯ | `kernel/self_evolution_cycle.py:218` `ReferenceKnowledgeBoundary` |
| Reflection / Self-Observer | ЕСТЬ | `kernel/reflection.py`, `kernel/runtime_reflection.py` |
| Memory Evolution | ЕСТЬ, БЕЗ sidecar | `kernel/memory_evolution.py` |
| Federation | ЕСТЬ | `kernel/federated_orchestrator.py`, `federated_executor.py` |
| Меж-инстансная шина | ЕСТЬ | `adapters/tcp_event_bus.py`, `INetworkTransport` |
| Слияние графов (CRDT) | ЕСТЬ | `adapters/crdt_graph.py` |
| Trust | ЕСТЬ | `kernel/identity.py` `ITrustRegistry` |
| Snapshot (8 слоёв) | ЕСТЬ | `composition/knowledge_persistence.py` |
| Graph query (плоский) | ЕСТЬ | `services/graph_query_engine.py` (~1880 строк) — методы `get_cluster`, `top_central`, `shortest_path`, `compound_query`, `cluster_by_tag`, `backlinks`, `forward_links` РЕАЛЬНО есть |
| **Multi-resolution / LOD** | **НЕТ** | — |
| **Abstraction sidecar (provenance при сжатии)** | **НЕТ** | — |
| **Cosmic perspective** | **НЕТ** | — |
| **Boundary владения (я/не-я)** | **НЕТ** | текущий Boundary — про «знаю/не знаю» |

**Вывод:** горизонтальная ось (федерация) закрыта раньше вертикальной. Строить её заново нечего. Пустая клетка = LOD.

## Цель

Научить ОДИН экземпляр отвечать знанием на подходящем уровне детализации с сохранением доказательной цепочки до исходных наблюдений.

```
ZOOM OUT                    ZOOM IN
SYSTEM (1 резюме)           EVIDENCE (147 фрагментов)
  ↓                           ↑
SUBSYSTEM (3)               NODE (1 узел)
  ↓                           ↑
CONCEPT (12)                CONCEPT (12 связанных)
  ↓                           ↑
NODE (147)                  SUBSYSTEM (3)
                              ↑
                          SYSTEM (1 резюме)
```

**Критерий успеха (proof-over-existence):** живой прогон — один запрос выдаёт 5 уровней; от резюме можно спуститься до узлов-источников; ни один шаг сжатия не удалил исходные данные.

## Границы (вне объёма)

- Не строим федерацию (она есть).
- Не создаём второй путь эволюции рядом с `services/skill_evolution.py`.
- Не внешний мета-слой / вторая ОС.
- Не переписываем `GraphQueryEngine` — LOD надстройка через порт.
- Не трогаем HARD-слой — агрегация только SOFT (O1).

## Этапы (K1–K8 соблюдаются)

| Этап | Что | Риск |
|---|---|---|
| **1** | Порт `IKnowledgeResolution` (`contracts/i_knowledge_resolution.py`) + сервис `services/knowledge_resolution.py` поверх `IGraphQuery`/`IGraphBuilder`. Методы: `view(query, level)`, `zoom_out(view)`, `zoom_in(item_id)`, `evidence_for(item_id)`. `provenance` никогда не пуст. | низкий (только чтение) |
| **2** | Abstraction sidecar в `ReferenceMemoryEvolution`: `sidecar_ref` на агрегат → 9-й слой снапшота. Забывание переносит в sidecar, не удаляет. | средний (формат снапшота) |
| **3** | Cosmic perspective: расширить `SelfObservationRecord` (доля графа, распределение активности, текущий уровень разрешения). Аддитивно. | низкий |
| **4** | Boundary владения: `+origin_of(node_id) -> LOCAL|FEDERATED|INGESTED`, `+can_accept(fragment)`. Агрегация не схлопывает узлы разного происхождения без метки в sidecar. | средний |

Каждый этап принимается только после Architecture Gate (`tests/architecture/`, 8 позитив + 6 негатив) + собственный негативный тест.

## Обоснование приоритета

Этап 1 первый (даёт словарь для остальных). Этап 4 последний (граница владения осмысленна только при многоуровневом знании с provenance).

## Статус исполнения (ADR-028, 2026-08-16)

**Этап 1 — DONE (verified).**
- Порт `contracts/i_knowledge_resolution.py` (K1), сервис `services/knowledge_resolution.py` (`ReferenceKnowledgeResolution`).
- Тесты `tests/knowledge/test_knowledge_resolution.py`: **7 passed**. Architecture Gate **27 passed**. Импорт-ось: CLEAN.

**Этап 2 — DONE (verified).**
- Артефакт предполагал построение sidecar с нуля; сверка показала `SemanticFact.source_episodes` **уже существует** (ТЗ-ME-01) → reuse, не дублирование (K5).
- Добавлен порт `consolidation_sidecar(episodes) -> Dict[fact_id, List[episode_id]]` в `contracts/i_memory_evolution.py` (K1, аддитивно).
- `kernel/memory_evolution.py`: `ReferenceMemoryEvolution.consolidation_sidecar` — deterministic (I-09), no mutation.
- `composition/knowledge_persistence.py`: 9-й слой `abstraction_sidecar` в `save` + `load_abstraction_sidecar()` (отдельно от узла, узел остаётся лёгким — по артефакту). Существующие вызовщики `save` не сломаны (параметр со дефолтом None).
- Тесты `tests/kernel/test_memory_evolution_sidecar.py`: **4 passed** (sidecar maps fact→exact episodes; survives snapshot round-trip; deterministic; port contract). Плюс регрессия `test_memory_evolution.py`: **10 passed** (все зелёные).
- Импорт-ось новых/изменённых файлов: CLEAN (K1).

**Этап 3 — DONE (verified).**
- Артефакт ссылался на `SelfObservationRecord` в `kernel/reflection.py`; сверка показала, что его **не существует** (reflection живёт в `ReferenceReflectionEngine.reflect()` → `ReflectionReport`). Создал `SelfObservationRecord` (frozen dataclass) в `contracts/cognitive_domain.py` (K1) — именно то, что артефакт описывал (доля графа / распределение активности / уровень разрешения).
- `kernel/reflection.py`: `ReferenceReflectionEngine.observe_scale()` — deterministic (I-09), ratios с полной точностью (3/15000 = 0.0002, не округляется до 0). Без нового микрокора (по артефакту — расширение, не второй класс).
- Тесты `tests/observability/test_reflection_cosmic_perspective.py`: **4 passed** (маленькая задача → точный ratio ≠ 0; нормализация активности к 1.0; 0 узлов безопасно; детерминизм). Плюс регрессия `test_reflection_engine.py`: **11 passed**.
- Импорт-ось: CLEAN (K1).

**Этап 4 — DONE (verified).**
- Сверка: `ReferenceKnowledgeBoundary` (kernel/self_evolution_cycle.py:218) УЖЕ есть (эпистемическая ось: KNOWN/UNKNOWN + abstain). Добавил ось ВЛАДЕНИЯ (по артефакту — расширение, не второй класс).
- `contracts/i_self_evolution_cycle.py`: `KnowledgeOrigin` (LOCAL/FEDERATED/INGESTED), `GraphFragment` (frozen VO), методы `origin_of` / `can_accept` в `IKnowledgeBoundary` (K1).
- `kernel/self_evolution_cycle.py`: `ReferenceKnowledgeBoundary.__init__` принимает опционально `graph` (IGraphBuilder) + `trust_registry` (ITrustRegistry); `origin_of` детерминированно возвращает LOCAL/FEDERATED/INGESTED; `can_accept` — trust-gated (фрагмент ниже порога → False). Добавлены экспорты `ITrustRegistry`/`KnowledgeOrigin`/`GraphFragment` в `contracts/__init__.py` (K1).
- Тесты `tests/kernel/test_knowledge_boundary_ownership.py`: **4 passed** (low-trust fragment rejected; sufficient-trust accepted; local node → LOCAL; federated via trust). Плюс регрессия `test_self_evolution_cycle.py`: **11 passed**.
- Импорт-ось: CLEAN (K1).

**ADR-028 — ALL 4 STAGES DONE (verified).** Multi-Resolution Knowledge реализовано поверх существующего substrate без дублирования (K5): порт разрешения (Этап 1), sidecar-слой снапшота (Этап 2), cosmic perspective (Этап 3), boundary владения (Этап 4). Architecture Gate 27/27, все новые тесты green.

