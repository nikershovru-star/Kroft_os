---
tags:
  - kroft
  - architecture
  - model-platform
  - adr
  - omniroute
created: 2026-07-31
status: draft
---

# ADR-006 — Model Platform

> Кандидат ADR-006 (нумерация унифицирована: см. [[ROADMAP]] / `docs/architecture/`).
> Связано: [[ADR-002 Contracts]], [[ADR-005 Resource Model]], [[ADR-007 Policy Platform]].

> Конкретная архитектура вертикали **MODEL PLATFORM** для Hermes OS v5.
> Дополняет [[Master Roadmap v2.0]] (видение/волны) и [[Hermes OS v5 — Architecture]]
> (целевая схема уровней). Фиксирует решения, которые не влезли в персональную
> память агента (лимит). **Не привязана к платному API** — только keyless/free.

## Статус

- **Кандидат ADR-033.** Ядро `hermes-kernel-v2` (GitHub) уже покрывает Wave 0/2/5
  (EventBus, Registry, Resilience ADR-031, Observability ADR-027). LLM-слоя в нём
  нет → эта заметка описывает, что добавить.
- Полигон реализации — `KnowledgeOS-v5`
  (`Obsidian Vault/02-Projects/KnowledgeOS-v5`), где **уже есть** слой портов
  `contracts/i_*.py` и адаптеры `adapters/*Adapter` (стиль: `ABC`+`@abstractmethod`,
  docstring «adapters may import contracts + stdlib»). Порта `ILlm` пока нет.

## Принципы (из Master Roadmap v2.0)

1. **Provider Agnostic** — доменный слой не знает про OpenAI/Ollama/OmniRoute.
   Смена backend = смена `base_url`.
2. **Contracts Before Code** — `ILlm` определяется до адаптеров.
3. **Observability First** — каждый вызов несёт телеметрию.
4. **Evolution Without Rewrites** — новый провайдер = новый адаптер, не правка ядра.

## Раздельные порты (не god-interface)

| Порт | Методы | Назначение |
| --- | --- | --- |
| `ILlm` | `complete()`, `stream()` | генерация текста/рассуждений |
| `IEmbedding` | `embed()` | векторизация (уже есть в полигоне) |
| `IModelMetadata` | `catalog()`, `capabilities()` | declared-контракты моделей |
| `IHealth` | `ping()`, `stats()` | живость провайдера |

> Нормализованный `LlmResponse` **обязан** нести `actual_model` — это решает
> double-routing (см. ниже).

## Модель запроса — многомерная, не грубая

Вместо `TaskType.REASONING / CHEAP` — `ModelQuery` с измерениями:

```python
@dataclass
class ModelQuery:
    task: str            # "reasoning" | "cheap" | "embed" | "json" | "local"
    reasoning: bool = False
    local: bool = False
    json_mode: bool = False
    cheap: bool = False
    context_window: int = 0
    preferred_provider: str | None = None
```

## Адаптеры (реализация портов)

| Адаптер | Бэкенд | Статус |
| --- | --- | --- |
| `OpenAiCompatibleClient` | любой OpenAI-совместимый endpoint (stdlib urllib) | MVP ✅ |
| `OmniRouteAdapter` | `http://localhost:20128/v1`, модель `auto` | MVP ✅ (keyless free, golden живой ping пройден) |
| `OllamaAdapter` | `http://localhost:11434/v1` | Wave 3 ✅ |

Все адаптеры импортируют только `contracts` + stdlib (как `OpenAIEmbeddingAdapter`
в полигоне). **Никакого `from openai import ...` в domain-слое.**

## Double-routing resolution

Проблема: и Hermes, и OmniRoute могут выбирать модель → кто выбрал?

- **MVP:** OmniRoute работает как **dumb-pipe**. Внутренний `auto` OmniRoute
  выключен; Hermes — единственный router (маппит `ModelQuery` → конкретная модель,
  напр. `Qoder/Kimi-K2-Free` или `OpenCode Zen`). `actual_model` = то, что послали.
- **Позже:** разрешить внутренний `auto` OmniRoute, парсить ответный заголовок
  `X-OmniRoute-Decision` и класть `actual_provider`/`actual_model` в `LlmResponse`.
  Обязательно для полноты eval/cast (иначе непонятно, какая модель реально ответила).

## Observability contract (Wave 1, переиспользуем Kernel v2 ADR-027)

`LlmResponse` возвращает:

```python
@dataclass
class LlmResponse:
    text: str
    trace_id: str
    provider: str
    model: str          # запрошенная
    actual_model: str   # реально ответившая (double-routing)
    tokens: int
    latency_ms: float
    cost: float         # 0.0 для keyless
    error: str | None
```

Без этих полей платформы нет (принцип Observability First).

## MVP v0.1 — чек-лист ✅

- [x] `contracts/i_llm.py` — `ILlm` + `IModelMetadata` + `IHealth` + `LlmResponse`
- [x] `adapters/model_platform.py` — `OpenAiCompatibleClient` (stdlib urllib)
- [x] `adapters/omni_route_adapter.py` — specialization, dumb-pipe (см. Wave 6)

## Wave 6 — Routing v2 (OmniRoute auto + X-OmniRoute-Decision) ✅

- [x] `OmniRouteAdapter(dumb_pipe=...)` — режим `dumb_pipe=False` отдаёт роутинг шлюзу (`auto`)
- [x] `OpenAiCompatibleClient._post` пробрасывает ответные заголовки
- [x] `LlmResponse` расширен: `actual_provider`, `decision`, `tokens_in/out`
- [x] double-routing: `actual_model`/`actual_provider`/`decision` из `x-omniroute-model`/`x-omniroute-provider`/`x-omniroute-decision` (второй источник truth)
- [x] golden live: `actual_model`/`actual_provider` реально приходят из заголовков OmniRoute

## Wave 3 — OllamaAdapter ✅
- [x] `pytest` — 454→464 passed, новые зелёные; axis-gate не нарушен
- [x] Зафиксировать ADR-033 (этот файл → статус `accepted`)

## Wave 3 — OllamaAdapter ✅

- [x] `adapters/ollama_adapter.py` — наследник `OpenAiCompatibleClient`, base_url `http://localhost:11434/v1`
- [x] declared local-каталог (llama3.2, phi4, qwen2.5, mistral) с capability-флагами
- [x] `tests/test_model_registry.py` — мок + golden ping (skipped, если Ollama не запущен)
- [x] Два полюса: OmniRoute = free online, Ollama = local offline

## Wave 4 — ModelRegistry ✅

- [x] `contracts/model_registry.py` — агрегирует каталоги OmniRoute + Ollama
- [x] `ModelRegistry.select(ModelQuery)` — учёт locality/reasoning/json/context
- [x] Тест: агрегация 2+ источников, select онлайн/локаль/но-мач

## Побочный фикс: Graph ACL (отдельный stage)

Минимальный фикс `infrastructure/graph_engine_extras.py::check_permission`:
ранний `return "default"` скрывал wildcard-грант (to=`"*"`), из-за чего
`test_graph_acl.py::test_wildcard_grant` падал. Переставил explicit→wildcard выше
fallback. Поднял 1 тест (7→6 падающих). Остальные 6 graph-тестов (import_export×3,
multiuser×1, semantic×2) — **другие pre-existing баги**, отдельный stage.

## Следующие волны

- **Wave 5** Policy Engine — **ТОЛЬКО ПРОЕКТ в следующей сессии, не код сейчас.**
  Открытые решения (см. `i_policy.py` sketch в Hermes-OS): где хранить бюджет
  (stateless vs persistent/sqlite/graph-node), fallback внутри Policy или обёртка
  вокруг `ILlm`, нужна ли очередь (async) или достаточно синхронного greedy.
- **Wave 6** Routing Engine v2 — OmniRoute `auto` + `X-OmniRoute-Decision`. ✅ ЗАКРЫТА.
- **Wave 7** Evaluation — golden dataset (вкл. KG-задачу через GraphQueryEngine).

## Известный техдолг (не размазывать фокус)

- **SSE streaming — отложить (Wave 7.5 / «пост-Policies»).** Текущий `stream()` —
  фейковый (yield from `complete()`). Настоящий SSE = новый транспортный слой:
  `_post` с `stream=true` + `Content-Type: text/event-stream`, парсер чанков
  (`data: {...}\n\n`), различие `message.content` vs `delta.content`, обработка
  `[DONE]`/ошибок внутри потока, сохранение `actual_model`/заголовков из финального
  чанка. Затронет `OpenAiCompatibleClient` + оба адаптера + тесты. Non-streaming
  покрывает ~80% use-case'ов. Записано как техдолг, не как текущая задача.

## Границы подсистемы (напоминание)

Model Platform вертикаль **closed**: ports → 2 adapters (OmniRoute + Ollama) →
registry → routing v2 (gateway-truth double-routing). История git: `b06f526`
(MVP+W3+W4+graph-fix), `0edbe24` (Wave 6). Заморожена — следующая сессия
входит в Wave 5 (Policy) как в новую вертикаль, с проектным документом, без
импульсивного кода.


## Guardrail против «вечной архитектуры»

Каждая волна (Wave 3 Provider / 4 Registry / 5 Policy / 6 Router / 7 Eval / 8 KG
Enrichment …) стартует **только** после того, как предыдущая показала ценность на
реальных прогонах. Никаких «спроектируем ещё 3 волны до первого вызова модели».

## Связи

- Видение/волны: [[Master Roadmap v2.0]]
- Целевая схема уровней: [[Hermes OS v5 — Architecture]]
- Полигон: `KnowledgeOS-v5/contracts/`, `KnowledgeOS-v5/adapters/`
- Ядро: `hermes-kernel-v2` (ADR-031 Resilience, ADR-027 Observability — переиспользовать)
