---
tags: [kroft, adr, memory, architecture, wave9]
created: 2026-07-31
status: accepted
---

# ADR-012 — Memory Platform (Wave 9)

**Status:** accepted
**Wave:** 9
**Commits:** `ce26ac2` (ports) · `47a8a1f` (adapters + service) · `fee3086` (tests)
**Verification:** 69 passed / 2 skipped (Wave 9) · 202 passed / 7 skipped (waves 5–9) · arch gate: 0 new violations

---

## 1. Context

Wave 8 (ADR-011) научила систему извлекать **факты** и складывать их в Graph. Но факт без
контекста мёртв: система знает «Rust — системный язык», и не знает, что пользователя зовут
Алиса, что она спрашивала про Rust пять минут назад и что предыдущая попытка ответа провалилась.

Чего не хватает по слоям:

| Слой | Чего нет сейчас |
|------|-----------------|
| Router (Wave 6) | `ModelQuery.prompt` уходит в LLM голым — модель не помнит диалог |
| Policy (Wave 5) | `PolicyContext.history: List[CallRecord]` всегда пустой — некому наполнить |
| Evaluation (Wave 7) | `Scorecard` живёт в процессе, тренды между сессиями не видны |
| Knowledge (Wave 8) | факты есть, но нет «что происходило вокруг факта» |

**Отдельно:** в проекте уже существует `services/session_store.py` (`SessionStore`, Stage 39/41) —
JSON-персистентность ходов агента. Это **не** порт: конкретный класс с `threading.Lock` и
привязкой к формату диска, без абстракции хранилища. Wave 9 его **не удаляет и не переписывает**
(вне scope, на нём висят тесты Stage 39/41), но новый код должен идти через порт `IMemoryStore`.
`SessionStore` помечается как legacy-путь; миграция — v0.5.

## 2. Decision

### 2.1 Пять типов памяти

| Тип | Назначение | Горизонт |
|-----|-----------|----------|
| **Working** | промежуточные результаты текущей задачи | секунды-минуты (TTL) |
| **Session** | текущий диалог, история сообщений | одна сессия |
| **Long-Term** | пережившее сессию (consolidation из Session) | бессрочно |
| **Semantic** | retrieval по смыслу | поверх Long-Term + Graph |
| **Procedural** | «как делать» — паттерны выполнения | бессрочно (Wave 10) |

**Ключевое решение:** это НЕ пять разных хранилищ и НЕ пять портов хранения. Тип памяти — это
**роль**, а не движок. Один порт `IMemoryStore` + разные экземпляры + теги
(`working` / `session` / `long_term` / `procedural`). Иначе получили бы 5 почти одинаковых
интерфейсов — абстракция без второй реализации у каждого (нарушение LAW 6).

Отдельные порты получают только те роли, у которых **другая сигнатура операции**:
- `ISemanticMemory` — поиск по смыслу (`search(text, limit)`), не по ключу;
- `IProceduralMemory` — запись/чтение паттернов выполнения (`record_procedure`/`recall_procedure`).

### 2.2 Definition of Done (Roadmap)

> Память работает независимо от конкретного движка.

Проверяется так: `MemoryPlatform` не импортирует ни одного адаптера; замена
`InMemoryMemoryStore` → SQLite (v0.5) → vector-store (v1.0) не трогает ни сервис, ни тесты
платформы (только фикстуру).

### 2.3 Порты (`contracts/i_memory.py`)

| Порт | Ответственность |
|------|-----------------|
| `IMemoryStore` | `put` / `get` / `query` / `delete_expired` / `compress` |
| `ISemanticMemory` | `search(text, limit)` — retrieval по смыслу |
| `IProceduralMemory` | `record_procedure` / `recall_procedure` — паттерны (Wave 10) |

Сущности: `MemoryItem` (frozen), `MemoryQuery`, `MemoryKind` (таксономия тегов),
`ConsolidationReport` (наблюдаемость consolidation).

### 2.4 Правило интеграции

```
Session Memory ──► Router.prompt        (контекст диалога)
Session Memory ──► consolidate() ──► Long-Term Memory
Long-Term + Graph ──► Semantic Memory ──► retrieval
```

**Интеграция с Knowledge (Wave 8) — через структурный порт, не импорт.**
В спеке волны значилось «Semantic Memory читает через `KnowledgePlatform.query()`». Такого
метода **нет**: `KnowledgePlatform` предоставляет `facts()` и `find(subject, predicate, object)`.
Прямой импорт всё равно был бы нарушением LAW 2 (`adapters`/`services` → другой сервис).
Решение: `SemanticMemoryStub` принимает `fact_source: Optional[Callable[[], Iterable[Any]]]` —
любой источник фактов. В проде туда передаётся `knowledge_platform.facts`. Read-only.

## 3. v0.1 ограничения (осознанные)

| Область | v0.1 | Дальше |
|---------|------|--------|
| Хранилище | `dict` + `threading.Lock` | SQLite (v0.5), vector-store (v1.0) |
| Semantic | keyword-overlap (без numpy/torch) | Ollama `/api/embed` (v1.0) |
| Compression | удаление `importance < threshold` | LLM-суммаризация (v1.0) |
| TTL | явный вызов `delete_expired()` | фоновая очистка (v1.0) |
| Procedural | порт + in-memory реализация | наполняется в Wave 10 (Workflow) |

**TTL без потока — сознательно.** Никакого cron и демона (stdlib-first): просроченный item
не возвращается из `get`/`query` (ленивая проверка), а физически удаляется явным
`delete_expired()`. Так «истёк» и «удалён» — разные события, оба наблюдаемы.

## 4. Слоевые границы (LAW 1 / LAW 2)

```
contracts/i_memory.py                → stdlib only
adapters/in_memory_memory_store.py   → contracts
adapters/semantic_memory_stub.py     → contracts   (fact_source инжектится как Callable)
services/memory_platform.py          → contracts   (НИКОГДА не импортирует adapters)
```

## 5. Consequences

**Плюсы**
- Router получает контекст диалога, не зная, где он хранится.
- Consolidation даёт явную границу «сессионный шум → долговременное знание», с отчётом (LAW 4).
- Compression считает удалённое (LAW 5) — видно, сколько памяти выброшено и почему.

**Минусы / долг**
- Пять типов памяти на одном порте — риск, что Semantic/Procedural со временем «перерастут»
  общий `IMemoryStore`. Осознанно: разделим, когда появится вторая реализация каждого.
- `SessionStore` (Stage 39/41) остаётся параллельным legacy-путём до v0.5.
- Keyword-based Semantic — заглушка; на длинных текстах будет давать шум.

## 6. Проверка (Phase F/G)

- `tests/test_memory_contract.py` — порты абстрактны, `MemoryItem` frozen, теги иммутабельны.
- `tests/test_in_memory_store.py` — TTL, compression, query по тегам/времени/паттерну.
- `tests/test_memory_platform.py` — consolidation, дополнение prompt, Semantic-заглушка.
- `tests/test_memory_integration.py` — Router + Session Memory: модель «помнит» контекст.
- `tests/test_memory_live.py` — gated `MEMORY_LIVE=1`: «Меня зовут Алиса» → «Как меня зовут?».

## 7. Связанные решения

- ADR-009 Policy Platform — `PolicyContext.history` может питаться из Session Memory.
- ADR-010 Evaluation Platform — Long-Term хранит историю scorecard для трендов.
- ADR-011 Knowledge Platform — источник фактов для Semantic Memory (read-only).
