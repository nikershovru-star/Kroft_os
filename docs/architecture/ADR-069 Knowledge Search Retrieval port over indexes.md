---
id: ADR-069
title: "Knowledge Search / Retrieval — deterministic port over existing indexes (ТЗ-SEARCH-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.92
confidence: high
tags: [search, retrieval, knowledge, determinism, LLM-free, I-09, K1, K6, K8]
---

# ADR-069 — Knowledge Search / Retrieval port over existing indexes (ТЗ-SEARCH-01)

## Context
Самоэволюция накопила semantic facts / эпизоды / soft policies; knowledge graph и
`ContentIndex` существуют (ТЗ-KNOW-001, ТЗ-ME-01). Но нет единого порта ИЗВЛЕЧЕНИЯ
знаний по запросу — именно это делает систему применимой (чтение накопленного обратно
для агента/пользователя).Первая платформенная волна применимости: SEARCH → RESEARCH →
PLUGIN.

K5-разведка (commit 0) подтвердила:
- `ISearchService` / `IQuery` / `SearchHit` **НЕ существовали** → создаём порт.
- `ContentIndex` (services/content_index.py), knowledge graph (`services/knowledge_graph/engine.py`,
  `IGraphEngine.nodes()`), `ILayeredMemory` (`get_semantic`/`get_episodes`/`get_normative`) —
  **УЖЕ существуют** → переиспользуем, НЕ дублируем индексы (one-port-per-boundary).

## Decision
Ввести `ISearchService` (contracts/i_search.py) + `SearchHit` (frozen VO) + `SearchScope`
(semantic/episodic/normative/graph/all). Reference-имплементация `ReferenceSearchService`
(kernel/search.py) — STANDALONE read-only сервис, конструируемый из `ILayeredMemory` +
опционального `IGraphEngine`. LLM-free, детерминированно (I-09).

Четыре reviewer-флага встроены (обязательны):
- **Флаг A** — НЕ индексировать «при каждом search». PURE-SCAN по источникам на каждый
  вызов; НЕ пишем в разделяемый `ContentIndex`. Token-overlap считается инлайн по тексту
  кандидата (детерминированно, без side-effect).
- **Флаг B** — ТОТАЛЬНЫЙ порядок ранжирования `(confidence desc, relevance desc, id asc)`.
  Стабильный тай-брейкер по id гарантирует идентичный результат при повторе (I-09).
- **Флаг C** — search НЕ проводится в `build_kernel`/`kernel.search()`. Сервис standalone;
  ядро не зависит от search (K6), god-factory (Флаг 1 OBS-01) не усугубляется. Advisor/
  reasoning context-request — отдельный будущий ТЗ.
- **Флаг D** — `SearchHit.causal: Optional[CausalMark]` (реальный тип, не object, урок
  Флага 1 LLM-01). Граф-ноды не имеют confidence/causal → дефолт (0.5 neutral) + `causal=None`,
  ранжирование единообразно между слоями.

## Consequences
- ✅ Единый детерминированный порт извлечения знаний без дублирования индексов.
- ✅ O1: read-only, не мутирует память/граф/контракты.
- ✅ K1: contracts + stdlib only (порт); kernel/search.py импортирует только contracts.
- ✅ K6: ядро не импортирует search; интеграция через порт.
- ✅ K8: negative gate-тесты (empty/no-match/unknown-scope → []).
- ⚠️ Non-scope: embedding/vector search, реальные embedding-модели — только token/keyword
  matching (LLM-free core). RESEARCH/PLUGIN — отдельные волны.
- ⚠️ Reference-долг (Флаг 1 LLM-02): contract-тесты на идеализированном payload; golden-файлы
  реальных wire-форматов — будущее. Multi-dimensional routing (Флаг 2 LLM-02) — тоже долг.

## Alternatives considered
- Расширить `ContentIndex` новым методом search-by-layer → ОТВЕРГНУТО: дублировало бы
  индекс и нарушало Флаг A (mutation per call).
- Провести search в `build_kernel` → ОТВЕРГНУТО: противоречит Флагу C и K6.

## Evidence
- `tests/test_knowledge_search.py`: 14 K8 тестов (relevant hits, total-order ranking,
  scope filter, negative, determinism, O1 read-only, causal real type, factory).
- Smoke: `search('choose blue')` → `semantic:sf-blue` (conf 0.9, rel 1.0); deterministic;
  empty → []; graph hit `causal=None`.
- Full suite GREEN, gate 14/14, akb-lint PASSED.
