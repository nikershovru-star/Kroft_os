---
id: ADR-070
title: "Research Service — deterministic research cycle over SEARCH (ТЗ-RESEARCH-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.92
confidence: high
tags: [research, retrieval, synthesis, determinism, LLM-free, I-09, I-10, K1, K6, K8, O1]
---

# ADR-070 — Research Service: deterministic cycle over SEARCH (ТЗ-RESEARCH-01)

## Context
SEARCH-01 дал детерминированное ИЗВЛЕЧЕНИЕ знаний (ISearchService). RESEARCH-01 применяет
извлечённое для СИНТЕЗА нового знания: сервис принимает цель/вопрос, извлекает релевантное
через ISearchService, агрегирует в `ResearchReport` и (опц.) записывает новые SOFT-знания в
память. Вторая платформенная волна (SEARCH → RESEARCH → PLUGIN). LLM-free по умолчанию (I-09);
опц. LLM-синтез через ILLMAdvisor с graceful fallback == retrieval-only (урок LLM-01/02).

K5-разведка (commit 0) подтвердила:
- `IResearchService` / `ResearchReport` / `ResearchGoal` **НЕ существовали** → создаём порт.
- `ISearchService` (SEARCH-01), `ILayeredMemory.commit_semantic`, `ILLMAdvisor`/`adapter_for`
  (LLM-01) — **УЖЕ существуют** → переиспользуем, НЕ дублируем порты (one-port-per-boundary).

## Decision
Ввести `IResearchService` (contracts/i_research.py) + `ResearchReport`/`ResearchGoal` (frozen VO
с реальными типами: `findings: Tuple[SearchHit]`, `causal: Optional[CausalMark]`, `provenance`).
`ReferenceResearchService` (kernel/research.py) — STANDALONE read-first сервис, конструируемый
из `ISearchService` (+ optional memory для SOFT write-back, + optional ILLMAdvisor). LLM-free
по умолчанию; опц. LLM-синтез с fallback.

Четыре обязательных ограничения (reviewer flags SEARCH-01 + ТЗ):
- **Флаг C (SEARCH-01)** — НЕ в `build_kernel`. Standalone фабрика `build_research_service`;
  ядро не зависит от research (K6), god-factory (Флаг 1 OBS-01) не усугубляется.
- **I-09 (determinism)** — LLM-free путь детерминирован: summary = top-finding content (search
  уже total-order по Флагу B SEARCH-01), aggregate confidence = mean. Повторный goal → идентичный
  report.
- **LLM-01/02 (fallback)** — опц. ILLMAdvisor; при LLMError/LLMTimeout → graceful fallback на
  retrieval-only summary (== результат без LLM). Fallback сам детерминирован.
- **O1 (SOFT-only write-back)** — если сервис пишет назад, ТОЛЬКО через `commit_semantic`
  (SOFT), под explicit opt-in `write_back=True`; НЕ трогает HARD/FSM/контракты.

## Consequences
- ✅ Единый детерминированный research-цикл поверх SEARCH без дублирования портов.
- ✅ K1: contracts + stdlib only (порт); kernel/research.py импортирует только contracts.
- ✅ K6: ядро не импортирует research; интеграция через порт + standalone фабрику.
- ✅ K8: negative gate-тесты (empty/no-match → empty report; LLM fallback == retrieval-only).
- ✅ O1: write-back только SOFT, opt-in.
- ⚠️ Non-scope: multi-step автономное планирование / RL — только однопроходный retrieve+aggregate;
  embedding/vector search — только keyword через ISearchService; реальные LLM-адаптеры в CI —
  только fake/mock advisor.

## Alternatives considered
- Встроить research в `build_kernel` → ОТВЕРГНУТО: противоречит Флагу C и K6.
- Дублировать поиск внутри research → ОТВЕРГНУТО: нарушало бы one-port-per-boundary и Флаг A SEARCH-01.

## Evidence
- `tests/test_research_service.py`: 13 K8 тестов (report+findings, determinism, aggregate conf,
  negative, LLM fallback == retrieval-only, O1 SOFT write-back, factory standalone).
- Smoke: `research('blue red')` → 2 findings, summary=top, agg conf 0.75, causal carried;
  determinism True; empty → empty report.
- Full suite GREEN, gate 14/14, akb-lint PASSED.
