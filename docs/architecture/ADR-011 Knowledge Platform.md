---
tags: [kroft, adr, knowledge, architecture, wave8]
created: 2026-07-31
status: accepted
supersedes: ADR-008 Knowledge Platform (draft)
---

# ADR-011 — Knowledge Platform (Wave 8)

**Status:** accepted (Wave 8 реализован: коммиты `ca32626`, `ba38ee4`, `cf453cd`;
40 passed / 1 skipped на `tests/test_knowledge_*.py`, арх-гейт без новых нарушений)
**Wave:** 8
**Заменяет:** ADR-008 «Knowledge Platform» (draft, 23 строки, без сигнатур) — тот документ был
намерением, этот — контрактом. ADR-008 остаётся в истории как *draft/superseded*.

---

## 1. Context

В системе уже есть Graph-движок (`infrastructure/graph_builder.py::InMemoryGraphBuilder`,
`services/graph_query_engine.py::GraphQueryEngine`, `infrastructure/graph_engine_extras.py`).
Он работает **изолированно**:

- не связан с **Model Platform** (Wave 3, ADR-033) — граф не умеет извлекать знания через LLM;
- не связан с **Evaluation Platform** (Wave 7, ADR-010) — в граф попадает всё, что положили,
  без измерения качества;
- не связан с **Policy/Routing** (Wave 5/6, ADR-009) — нет управляемого выбора модели для extraction.

Как следствие граф — это **свалка утверждений**, а не доверенный ресурс. Нельзя ответить на вопросы:
«откуда это ребро?», «кто его добавил?», «насколько мы в нём уверены?», «что изменилось со вчера?».

## 2. Decision

Wave 8 превращает Graph в **платформу знаний** с одним жёстким правилом:

> **LLM создаёт только гипотезы. Knowledge Graph принимает только проверенные факты.**

### 2.1 Pipeline

```
Document → Chunk → (Embedding*) → Entity Extraction → Relation Discovery
         → Evidence → Validation → Knowledge Graph
```
`*` Embedding в v0.1 не используется (уже есть `contracts/embedding.py` / `services/semantic_index.py`);
подключается в v1.0 для дедупликации сущностей.

### 2.2 Правило интеграции (обязательный порядок)

```
Router (Wave 6) → LLM (Wave 3) → Hypothesis → Evaluation (Wave 7) → Fact → Graph
                    ^ Policy (Wave 5) выбирает модель по reasoning=True
```

Гипотеза **никогда** не попадает в граф напрямую. Между ними всегда стоит `IValidator`.

### 2.3 Порты (contracts/i_knowledge.py)

| Порт | Ответственность |
|------|-----------------|
| `IEntityExtractor` | текст → сущности и **гипотезы** связей (через Router/LLM) |
| `IValidator` | гипотеза + Scorecard → `Fact` (или отказ) |
| `IFactChecker` | оценка достоверности одной гипотезы: `float` 0.0–1.0 |
| `IKnowledgeGraph` | хранение **только** `Fact`: `add_fact`, `facts`, `find` |

### 2.4 Сущности

| Сущность | Поля | Иммутабельность |
|----------|------|-----------------|
| `Entity` | `name, type, evidence, source` | frozen |
| `Relation` | `subject, predicate, object` | frozen |
| `Hypothesis` | `subject, predicate, object, source, evidence, confidence` | frozen |
| `Fact` | `subject, predicate, object, source, evidence, confidence, history` | frozen, `history` — **tuple** (append-only) |

`Fact.history` — кортеж записей `{timestamp, action, actor}`. Изменение факта = **новый объект**
через `fact.with_history(action, actor)`; мутации на месте невозможны (LAW 3).

### 2.5 Definition of Done (Roadmap)

Каждая связь в графе несёт:
1. **источник** — `Fact.source` (`model_id` / `document_id`);
2. **доказательство** — `Fact.evidence` (raw text чанка / `trace_id`);
3. **уровень доверия** — `Fact.confidence` (0.0–1.0, из Evaluation);
4. **историю изменений** — `Fact.history` (append-only).

## 3. v0.1 ограничения (осознанные, не баги)

| Область | v0.1 | v1.0 |
|---------|------|------|
| Chunking | split по `\n\n`, stdlib-only (LAW: stdlib-first) | sentence-aware split |
| Validation | эвристика: 3 непустых поля + `confidence ≥ 0.5` из Evaluation | rubric-based LLM-judge |
| Порог записи в граф | `confidence > 0.7` → Fact; иначе гипотеза отбрасывается | адаптивный порог по домену |
| Embedding | не используется | дедупликация сущностей |
| `IEntityExtractor` | 1 реализация (LLM) | 2-я — rule-based regex extractor (LAW 6) |

## 4. Слоевые границы (LAW 1 / LAW 2)

```
contracts/i_knowledge.py      → stdlib + contracts.*        (порты и сущности)
adapters/llm_entity_extractor.py → contracts.*              (Router инжектится как Callable)
adapters/graph_knowledge_store.py → contracts.*             (IGraphBuilder инжектится, не импортируется из infrastructure)
services/knowledge_platform.py   → contracts.*              (НИКОГДА не импортирует adapters)
```

`KnowledgePlatform` принимает `IEntityExtractor`, `IValidator`, `IKnowledgeGraph` — **только порты**.
Router не приходит в сервис вовсе: он инжектится в *адаптер* extraction как
`Callable[[ModelQuery], LlmResponse]` (структурный порт, как `BenchmarkRunner` в Wave 7).

## 5. Consequences

**Плюсы**
- Граф становится доверенным ресурсом: любое ребро объяснимо (LAW 4).
- Качество extraction измеряется тем же Scorecard, что и routing (LAW 5).
- Пороговое правило — единственная точка, где «мнение модели» превращается в «знание системы».

**Минусы / долг**
- v0.1-эвристика валидации пропускает синтаксически корректный, но семантически ложный факт.
  Признано осознанно: порог 0.7 + запись confidence позволяют потом измерить, сколько мусора прошло.
- Существующий Graph-движок не переписывается — интеграция через адаптер. Внутренние баги
  6 untracked graph-тестов (`test_graph_acl`, `test_graph_import_export`, …) — **вне scope Wave 8**.

## 6. Проверка (Phase E/F)

- `tests/test_knowledge_contract.py` — порты абстрактны, `Fact` frozen, история append-only.
- `tests/test_knowledge_platform.py` — моки: LLM → JSON, Validator пропускает/блокирует, Fact в графе.
- `tests/test_knowledge_integration.py` — реальный `Router` + `PolicyEngine` + мок-ILlm + Graph.
- `tests/test_knowledge_live.py` — gated `KNOWLEDGE_LIVE=1`, реальный OmniRoute/Ollama.

## 7. Связанные решения

- ADR-033 Model Platform (Wave 3) — источник LLM.
- ADR-009 Policy Platform (Wave 5) — выбор модели для extraction (`reasoning=True`).
- ADR-010 Evaluation Platform (Wave 7) — источник `confidence`.
- ADR-008 Knowledge Platform (draft) — **superseded** данным ADR.
