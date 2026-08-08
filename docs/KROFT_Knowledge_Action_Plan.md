---
id: KROFT_KNOWLEDGE_ACTION_PLAN
title: Action Plan — KROFT Knowledge Base (Atomic Q&A)
status: draft
date: 2026-08-08
depends_on: KROFT_Knowledge_Base_Proposal.md, ADR-100, ADR-069, ADR-091
---

# Action Plan — KROFT Knowledge Base (Atomic Q&A)

> План реализации стратегии из `KROFT_Knowledge_Base_Proposal.md`. Цель — обучающая база
> атомарных знаний (Вопрос → Ответ → Пример → Связи) как отдельный слой `KROFT_KNOWLEDGE/`,
> НЕ смешиваемый с проектными решениями Vault. Все шаги — через существующий pipeline
> (K5/K6): reuse `KnowledgeEngine`, `ContentIndex`, `InMemoryGraphEngine`, ingestion →
> graph → persistence → retrieval. Без параллельных реализаций.

## Принципы (из послания владельца)
1. **Качество > количество.** 10k связанных/проверенных > 100k плохо структурированных.
2. **Не Document→LLM→DB.** Source→Ingestion→Extraction→Normalization→Node→Relations→
   Validation→Indexing→Retrieval→Evaluation→Graph.
3. **Отдельный слой.** `KROFT_KNOWLEDGE/` ≠ Vault-проектные заметки.
4. **Сначала Schema + 500–1000 эталонных Q&A, потом масштаб.**
5. **Graceful / verifiable.** Каждый шаг доказывается прогоном через реальный pipeline.

## Шаг 0 — Knowledge Schema + Node Format (базис)
**Задача:** зафиксировать структуру атомарного знания и типы связей.
- Поля node (из Предложения §1): `ID, TYPE, QUESTION, ANSWER, EXAMPLE, COUNTEREXAMPLE,
  SOURCE, SOURCE_TYPE, DATE, CONFIDENCE, TAGS, RELATED_CONCEPTS, PARENT_CONCEPT,
  CHILD_CONCEPTS, CONFLICTS`.
- Типы знаний (§13): FACTUAL / CONCEPTUAL / PROCEDURAL / EXPERIENTIAL / META / SELF / DECISIONAL.
- Типы вопросов (§8): DEFINITION / WHY / HOW / WHEN / WHEN_NOT / COMPARE / CAUSE / EFFECT /
  EXAMPLE / COUNTEREXAMPLE / TRADEOFF / FAILURE / DEBUG / DESIGN / DECISION / VERIFY / CONNECT /
  PREDICT / SCENARIO.
- Связи: `RELATED`, `PARENT`, `CHILD`, `CONFLICTS`, `SOURCE`.
**Результат:** `docs/KROFT_KNOWLEDGE/schema.md` (спецификация) + решение: хранить как
markdown-ноды (существующий `ContentIndex` парсит markdown) ИЛИ как структурированный
JSON для прямого ingestion в `InMemoryGraphEngine`.
**Verification:** schema проходит review владельца; пример node парсится ingestion-пайплайном.

## Шаг 1 — KROFT_KNOWLEDGE_PACK_V1 (500–1000 эталонных Q&A)
**Задача:** сгенерировать первый пакет по 15 папкам (§15):
`01_AI … 15_PROCEDURES`. Распределение ~60–70 Q&A на папку (итого ~1000), с миксом типов
вопросов (не только «Что такое X?»).
- Источники (§3–5): книги Tier 1, 50–100 фундаментальных papers, курсы, YouTube-transcripts.
- Формат каждого `.md` — готовый Knowledge Node (§1, §7).
- Приоритет тем, уже релевантных KROFT: OS/Systems, Software Architecture, Knowledge
  Management, Agent Systems, RAG, Security, SRE (из Slice 1–9 arc).
**Результат:** папка `KROFT_KNOWLEDGE/` с ~1000 node-файлов.
**Verification:** каждый node валиден по Schema (§0); lint-скрипт проверяет обязательные поля.
**Объём:** большая генерация — требует отдельного подтверждения владельца (делать ли
пакет целиком в одном заходе ИЛИ итеративно по папкам).

## Шаг 2 — Ingestion в существующий KnowledgeEngine
**Задача:** прогнать `KROFT_KNOWLEDGE/` через `services/knowledge_engine.build_knowledge_engine`
+ `services/content_index.ContentIndex` (K5 reuse, как в `run_kroft`).
- `ObsidianVaultReader` НЕ использовать (это проектный Vault) — сделать лёгкий
  `KnowledgePackReader` (читает `KROFT_KNOWLEDGE/*.md`) ИЛИ reuse `ContentIndex` напрямую.
- Каждый node → entity в `InMemoryGraphEngine` + edges из `RELATED/PARENT/CHILD/CONFLICTS`.
**Результат:** граф знаний из ~1000 nodes заполнен.
**Verification:** `engine.graph.stats()` показывает ожидаемое число nodes/edges; тест
`test_knowledge_pack_ingest.py` зелёный.

## Шаг 3 — Retrieval + Graph Query
**Задача:** проверить, что KROFT реально отвечает на вопросы из базы.
- Semantic retrieval (embedding, Slice 9) + keyword (BM25, Slice 9 fallback) по nodes.
- Graph traversal: «что связано с RAG?» через `RELATED` edges.
- `find_hidden_connections` (если применимо из KnowledgeOS-v5) — опц.
**Результат:** запрос «Что такое RAG и когда предпочтительнее fine-tuning?» возвращает
релевантные nodes (§7/§10/§11).
**Verification:** `test_knowledge_pack_retrieval.py` — spy/real retrieval находит node по
смыслу (не только по ключевым словам).

## Шаг 4 — Качество / Evaluation
**Задача:** метрики по §7.27 (factual/retrieval/citation accuracy, hallucination rate).
- `Confidence` из node (§1) → вес при retrieval.
- Contradiction management (§12): при `CONFLICTS` — не слепо merge, а показать оба + источник.
**Результат:** baseline метрик на 50 held-out вопросах.
**Verification:** `test_knowledge_pack_evaluation.py` — precision@k, наличие citation/source.

## Шаг 5 — Масштабирование (после Шаг 0–4)
**Задача:** только если pipeline доказал обучение — расширить до 10–20k Q&A (§8).
- Автоматизировать генерацию из книг/papers (через transcript→Q&A, §7.35) с человеком в контуре.
- Добавить слои SELF (§11) и EXPERIENCE (§12) — KROFT сохраняет опыт своих операций.
**Результат:** полная `KROFT_KNOWLEDGE` база.
**Verification:** полный suite + knowledge-pack тесты green; arch-gate clean.

## Риски / Consciously deferred
- **Размер генерации (Шаг 1).** 500–1000 Q&A — большой объём; требует подтверждения
  владельца (один заход ИЛИ итеративно). Не делать «втихую».
- **Source reliability.** Внешние книги/papers — не всегда авторитетны; поле `CONFIDENCE` +
  `SOURCE_TYPE` обязательно.
- **Не смешивать с Vault.** `KROFT_KNOWLEDGE/` — отдельный слой; проектные ADR/заметки Vault
  не трогать.
- **LLM-генерация Q&A.** Если использовать LLM для генерации пакета — только как черновик,
  человек (владелец) в контуре верификации (KROFT-принцип: не выдумывать, Retrieve→Verify).
- **Persistence формата.** Node хранить как markdown (human-readable) ИЛИ JSON (machine) —
  решается в Шаг 0; не дублировать.

## Коммиты (по готовности, атомарно)
- `docs(knowledge): knowledge schema + node format (KROFT_KNOWLEDGE)`
- `feat(knowledge): KROFT_KNOWLEDGE_PACK_V1 — N reference Q&A` (по папкам)
- `feat(knowledge): ingest KROFT_KNOWLEDGE into KnowledgeEngine`
- `test(knowledge): retrieval + evaluation on knowledge pack`
- `docs(knowledge): scale to 10–20k Q&A` (после подтверждения)

## Статус
- [x] Предложение сохранено (`KROFT_Knowledge_Base_Proposal.md`)
- [ ] Шаг 0 — Schema (ожидает подтверждения владельца)
- [ ] Шаг 1 — Pack V1 (ожидает подтверждения объёма)
- [ ] Шаг 2–5 — последующие
