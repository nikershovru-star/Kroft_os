---
tags:
  - kroft
  - roadmap
  - vision
  - architecture
created: 2026-07-31
status: shipped
completed: 2026-07-31
---

# KROFT_OS — Master Architecture Roadmap

> **Autonomous Intelligence Operating System.** Источник — сообщения пользователя
> (2026-07-31): десять принципов + 14 волн + 5 этапов + новое позиционирование
> «KROFT_OS как ОС, а не очередной AI-проект». Ниже — видение **и** его приземлённая
> привязка к реальным репозиториям, чтобы не скатиться в «вечную архитектуру».

## Новое позиционирование (2026-07-31)

**Полное название:** KROFT_OS — Autonomous Intelligence Operating System
(или Operating System for Intelligent Agents).

**Видение:** модульная операционная система для построения автономных
интеллектуальных систем. Микроядро + платформы ресурсов + когнитивные сервисы,
позволяющие создавать агентов, приложения и экосистемы, способные обучаться,
адаптироваться и развиваться **без привязки к конкретным моделям ИИ или провайдерам**.

**Миссия:** построить открытую ОС нового поколения, где интеллект — системный
ресурс, как память, ФС или сеть в классических ОС.

**Долгосрочная цель:** не «ещё один AI-агент» и не «ещё один framework», а ОС:

```
                KROFT_OS
              Operating System
                     │
      ┌──────────────┼──────────────┐
      │              │              │
  Model Platform  Memory Platform  Knowledge Platform
      │              │              │
      ├──────────────┼──────────────┤
                     │
              Workflow Platform
                     │
              Tool Platform
                     │
              Security Platform
                     │
            Observability Platform
                     │
             Plugin Platform
                     │
                Applications
```

**Что становится приложениями** (поверх KROFT_OS, а не отдельными проектами):
MarketMind, Research Assistant, KnowledgeOS, Hermes, Desktop Assistant,
Automation Hub, RAG-системы, корпоративные AI-агенты.

**Эволюция:** раньше Hermes / KnowledgeOS / MarketMind / Desktop — четыре
отдельных проекта. Теперь — приложения одной экосистемы поверх Shared Kernel.
Это делает архитектуру целостной и упрощает развитие.

**Главная цель одной фразой:** KROFT_OS — открытая ОС для интеллектуальных систем,
объединяющая память, знания, модели, инструменты и рабочие процессы в единую
расширяемую платформу.

## Десять принципов (канон)

1. **Kernel First** — ядро строится до всего остального; модели подключаются позже как сервис.
2. **Contracts Before Code** — порты определяются до адаптеров.
3. **Observability First** — каждый сервис публикует TraceID/RequestID/Latency/Duration/Errors/Retries/Resource Usage. Без телеметрии платформы нет.
4. **Everything is a Resource** — файлы, память, граф, планировщик, инструменты, наблюдаемость, безопасность — равноправные сервисы.
5. **Event Driven** — взаимодействие через события, не жёсткие вызовы.
6. **Policy Driven** — поведение определяется политиками (Privacy/Security/Budget/Compliance/Offline/Tenant).
7. **Provider Agnostic** — ни один доменный слой не знает про OpenAI/Ollama/OmniRoute. Смена backend = смена base_url.
8. **Evidence Before Knowledge** — LLM генерирует только гипотезу; запись в KG идёт только после Evidence→Validation.
9. **Learning Through Metrics** — улучшения на основе измерений, не на угадывании.
10. **Evolution Without Rewrites** — расширение через новые адаптеры/политики, а не переписывание ядра.

## Четырнадцать волн (Waves)

| Wave | Название | Суть | Статус |
| --- | --- | --- | --- |
| 0 | Kernel Foundation | Event Bus, Service Registry, DI, Config, Lifecycle, Health | ✅ |
| 1 | Observability | traces/metrics/logs из каждого сервиса | ✅ |
| 2 | Contracts | LlmPort, EmbeddingPort, MemoryPort, GraphPort, ToolPort, StoragePort, WorkflowPort + Contract/Golden/Compat | ✅ |
| 3 | Provider Layer | Model: OmniRoute/Ollama/OpenAI/LiteLLM/LM Studio; Memory: Mem0/Zep/Local/Redis; Knowledge: Neo4j/NetworkX/Obsidian/Graphiti | ✅ ADR-006/033 |
| 4 | Registry | Model/Tool/Memory/Plugin/Workflow/Prompt каталоги | ✅ |
| 5 | Policy Engine | Privacy/Security/Budget/Compliance/Offline/Tenant | ✅ ADR-009 (5.1 Privacy, 5.2 Security) |
| 6 | Routing Engine | Task→Policy→Registry→Router→Provider (роутит не только модели) | ✅ |
| 7 | Evaluation Platform | бенчмарки Memory/Graph/Model/Workflow | ✅ ADR-010 |
| 8 | Knowledge Platform | Docs→Chunk→Embed→Entities→Relations→Validation→KG | ✅ **ADR-011** |
| 9 | Memory Platform | Working/Session/Long-term/Semantic/Procedural + TTL | ✅ **ADR-012** |
| 10 | **Workflow** (ADR-013) | ✅ `565e4f4` `4f8fc1b` `7e5c2ad` `01780c9` |
| 11 | **Agent Platform** (ADR-014) | ✅ `aa3196d` `b5f115f` `a31d6a3` `ea1de10` |
| 12 | **Learning Platform** (ADR-015) | ✅ `610b628` `b2e6801` `aa63912` `a46efa2` |
| 13 | **Optimization Platform** (ADR-016) | ✅ `05c6b04` `23ae648` `e119e2a` `a02979d` |
| 14 | **Autonomous Hermes** (ADR-017) | ✅ `66a1764` `ff89237` `42d6020` `427f3f0` |

> **All 14 waves shipped (2026-07-31).** Arch-gate green (0 violations). Regression waves 5–14: **225 passed / 10 skipped**. See RELEASES.md `[v1.0]`.
>
> **Bootstrap Initiative (2026-07-31, ADR-018):** единый `bootstrap.py` Composition Root + Runtime Lifecycle. Ядро грузится БЕЗ внешнего backend (MockLlmAdapter — обязательный fallback). Smoke S1–S4 пройдены. `bootstrap.py` — новый канонический вход в ОС.

## Пять этапов

- **Stage 1 — Foundation** (Wave 0–2, 2–4 нед): минимально, но *работоспособно*.
- **Stage 2 — Infrastructure** (Wave 3–6, 3–5 нед): провайдеры, реестр, политики, роутер.
- **Stage 3 — Intelligence** (Wave 7–10, 4–6 нед): eval, KG, память, агенты.
- **Stage 4 — Agents** (Wave 11–12, 2–4 нед).
- **Stage 5 — Autonomous** (Wave 13–14, непрерывно).

> **Критерий зрелости (пользователь):** Этап 1 должен быть минимальным, но
> работоспособным. Главная ловушка — «вечная архитектура»: бесконечное
> проектирование вместо работающего куска.

## Приземлённая привязка к репозиториям (исполняемый план)

### Утверждённая топология (реальность, 2026-07-31)

- **`hermes-kernel-v2`** (GitHub, nikershovru-star) — микроядро Python, Clean
  Architecture, ADR-001..032, tach axis-gate, уже покрывает Wave 0/2/5
  (EventBus, Registry, Resilience ADR-031, Observability ADR-027). LLM-слоя нет →
  кандидат на ADR-033.
- **`KnowledgeOS-v5`** (`Obsidian Vault/02-Projects/KnowledgeOS-v5`) — **полигон**.
  Уже есть `contracts/i_*.py` (стиль: `ABC`+`@abstractmethod`, docstring
  «adapters may import contracts + stdlib») и `adapters/*Adapter`
  (`OpenAIEmbeddingAdapter` через stdlib urllib, `MockEmbeddingAdapter` для тестов).
  Порта `ILlm` **нет** — реальная пустая ниша. `AgentService` — rule-based
  intent router (PATTERNS), не вызывает LLM. `GraphQueryEngine` — реальный объект.
- **OmniRoute** — внешний OSS Model Platform. Первый Model Provider адаптер
  (keyless free-модели, `http://localhost:20128/v1`, модель `auto`). **Один из
  адаптеров, не привилегированный.**

### Stage 1 — уже выполнено частично (не переписываем)
Wave 0/1/2 закрыты ядром v2 + портами KnowledgeOS-v5. Достраиваем недостающее в полигоне.

### Stage 2 — MVP v0.1 (стартуем сейчас)

1. `contracts/i_llm.py` — `ILlm` (раздельно от Embedding): `complete()`, `stream()`,
   `IModelMetadata`, `IHealth`. Нормализованный `LlmResponse` **обязан** нести
   `actual_model` (решение double-routing).
2. `adapters/model_platform.py` — `OpenAiCompatibleClient` (stdlib urllib, как в
   `embedding.py`): OmniRoute @:20128, `api_key` любой.
3. `adapters/omni_route_adapter.py` — тонкий specialization: маппит `ModelQuery` →
   конкретная модель (dumb-pipe, внутренний `auto` OmniRoute выключен в MVP), парсит
   `X-OmniRoute-Decision` → `actual_model`.
4. Observability MVP: `LlmResponse` несёт `trace_id, tokens, latency, cost,
   provider, model, error`.
5. Contract tests: `tests/test_llm_adapter.py` (мок, без сети) → pytest зелёный,
   axis-gate не нарушен.
6. **Golden test**: реальный keyless `auto` ping OmniRoute (доказательство фундамента).

### Double-routing resolution
MVP: OmniRoute = dumb-pipe (Hermes — единственный router, внутренний `auto` выключен).
Позже: парсить `X-OmniRoute-Decision` и класть `actual_provider`/`actual_model` в
`LlmResponse` (обязательно для полноты eval/cast).

### Guardrail против «вечной архитектуры»
Каждая волна (Wave 3..14) стартует **только** после того, как предыдущая показала
ценность на реальных прогонах. Никаких «спроектируем ещё 3 волны до первого вызова».

## Резолюция открытых вопросов

- **Что даёт OmniRoute без ключей?** Keyless free-провайдеры (OpenCode Zen,
  Pollinations, Qoder/Kimi-K2, OpenRouter :free), auto-fallback при 429, сжатие
  токенов 15–95% (RTK+Caveman). НЕ даёт качества платных (Opus/GPT-5) и безлимита.
- **Автономия агента:** `hermes config set approvals.mode off` + перезапуск сессии
  (или `hermes --yolo`). Secret redaction — отдельный независимый тумблер, вкл.
- **Совместимость с ядром:** через `ILlm`-адаптер на localhost:20128; домен чист,
  axis-gate зелёный.
