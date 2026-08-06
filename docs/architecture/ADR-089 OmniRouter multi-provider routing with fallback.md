---
id: ADR-089
title: OmniRouter — multi-provider LLM routing with auto-select + fallback (ТЗ-OMNI-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-065   # LLM-01 advisor boundary (retrieval-only fallback)
  - ADR-068   # LLM-02 OpenAI-compatible adapter (IHttpTransport)
  - ADR-079   # LLM-LIVE-01 client factory
  - ADR-087   # LIVE-01 runnable launch + persistence
  - ADR-088   # LIVE-01 extended living core (auto/none, autosave, SIGINT)
decision: >-
  ТЗ-LLM-LIVE-01 дал один OpenAI-совместимый эндпоинт (Ollama). ТЗ-OMNI-01 расширяет до
  упорядоченного списка провайдеров с автовыбором и fallback. Новый порт IModelRouter
  (contracts/i_model_router.py) расширяет ILlm (KROFT one-port-per-boundary: НЕ создаём
  второй LLM-порт) и добавляет providers (list[ProviderSpec]) + route(query)->ILlm.
  Reference impl OmniRouter (composition/omni_router.py) строит упорядоченный список
  OpenAiCompatibleClient (по ProviderSpec, сортировка по priority, стабильная) поверх
  общего HttpTransport (stdlib urllib). complete() перебирает по priority, fallback на
  LLMError/LLMTimeout; все сбои -> LLMError (ядро идёт retrieval-only, LLM-01). Локальный
  Ollama первым (detect_local_ollama, priority=-100); облачные только при наличии ключей
  (api_key_env, иначе пропускаются на сборке). build_llm_client(providers=...) возвращает
  OmniRouter; роутер сам ILlm -> adapter_for/ядро принимают его без изменений. Детерминизм
  (priority-порядок, I-09). K6: composition может импортировать adapters (gate rule);
  домен без SDK; сеть через IHttpTransport. K5: переиспользованы HttpTransport,
  OpenAiCompatibleClient, detect_local_ollama, build_llm_client, ILLMAdvisor/adapter_for;
  НЕ дублирован adapters/router.py (Wave 5 PolicyEngine-роутер — другой слой/назначение).
evidence_level: V
addresses:
  - TZ-OMNI-01
---

## Context
LLM-LIVE-01 подключил локальный Ollama как единственный эндпоинт. Для Этапа 2 (multi-provider)
нужен автовыбор и fallback: локальный первым (offline-friendly, keyless), облачные по API-ключам
как резерв, все сбои -> retrieval-only (LLM-01). Без SDK в домене, с детерминированным порядком.

## Decision
- **IModelRouter(ILlm)** (contracts/i_model_router.py): `providers` property + `route(query)->ILlm`;
  наследует `complete`/`stream` от ILlm. ProviderSpec (frozen VO): name, base_url, api_key_env,
  priority, model.
- **OmniRouter(IModelRouter)** (composition/omni_router.py): клиенты сортируются по priority
  (стабильно, I-09); `complete()` пробует каждый, fallback на LLMError/LLMTimeout; все сбои ->
  LLMError; `stream()` аналогично. `route()` возвращает первый по priority.
- **build_omni_router(providers, include_local_ollama=True)**: локальный Ollama prepended
  (priority -100, если detect_local_ollama); облачные с пустым api_key_env пропускаются.
- **build_llm_client(providers=...)**: при непустом providers возвращает OmniRouter; иначе
  прежнее поведение (один клиент) — backward-compat.
- **K6**: OmniRouter в composition/ (импортирует adapters/openai_compatible — разрешено
  import_matrix: composition -> adapters); сеть только через IHttpTransport.

## Consequences
- Ядро получает одного советника (OmniRouter) с автовыбором + fallback; без моделей/ключей
  complete() бросает LLMError -> retrieval-only (не crash).
- Non-scope (post-MVP): реальные облачные вызовы в CI (тесты на FakeTransport/in-process),
  балансировка по стоимости/латентности, кеширование, health-пробинг облачных (сейчас
  детерминированный priority, без живого ping).
