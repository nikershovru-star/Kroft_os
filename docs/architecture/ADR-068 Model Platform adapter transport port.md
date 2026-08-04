---
id: ADR-068
title: "Model Platform — concrete OpenAI-compatible ILlm adapter + transport port (ТЗ-LLM-02)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
risk: low
related: [ADR-065, ADR-033, TZ-LLM-01, TZ-OBS-01, I-10, K1, K6, K8, O1]
addresses: [TЗ-LLM-02, I-10, FLAG-2-OBS-01, K1, K6, K8]
---

## 1. Context
LLM-01 доказал advisor+fallback на mock; OBS-01 оставил `llm.fallback_rate` без hook
(Флаг 2). Но конкретного `ILlm`-адаптера нет — «LLM как взаимозаменяемый инструмент»
частично декларация. ТЗ-LLM-02 строит ОДИН concrete adapter (`OpenAiCompatibleClient`)
поверх pluggable `IHttpTransport` порта, чтобы contract-тесты шли БЕЗ живой модели/сети,
и прогоняет его через `adapter_for -> ILLMAdvisor -> kernel`, доказывая bridge + graceful
fallback на реальном-по-форме клиенте. Заодно кормит `llm.fallback_rate` (Флаг 2 OBS-01).

## 2. Decision
- **`IHttpTransport` порт** (contracts/i_http.py): `request(method,url,headers,body,timeout)
  -> HttpResponse` + `HttpResponse` (frozen VO) + `TransportError`/`TransportTimeout`.
  ОТДЕЛЬНАЯ граница от `i_llm.ILlm` (model-port) / `i_telemetry` / `i_observability` —
  KROFT one-port-per-boundary. Адаптеры НЕ импортируют requests/httpx в domain (K6):
  вся сеть идёт через injectable transport (тестируется fake).
- **`OpenAiCompatibleClient(ILlm)`** (adapters/openai_compatible.py): concrete adapter.
  `ModelQuery.prompt -> OpenAI /chat/completions` payload (json_mode поддержан).
  transport errors маппятся в advisor-словарь: `TransportTimeout -> LLMTimeout`,
  `TransportError`/non-2xx/malformed `-> LLMError`. `LlmResponse.actual_model`
  ОБЯЗАТЕЛЕН (ADR-065 double-routing): = requested model или gateway-resolved из
  заголовка (`x-omniroute-provider`/`model`). K1: adapters импортируют только
  contracts + stdlib (НЕТ provider SDK).
- **Bridge уже готов (LLM-01):** `adapter_for(ILlm)` возвращает `ILLMAdvisor`. В ТЗ-LLM-02
  уточнён: `adapter_for` НЕ перепаковывает `LLMTimeout` в `LLMError` — пробрасывает
  advisor-ошибки как есть (timeout vs error distinct, O1/I-10 семантика).
- **Hook `llm.fallback_rate`** (Флаг 2 OBS-01): `LLMAdvisorReasoning`/`LLMAdvisorPlanner`
  в `except (LLMError, LLMTimeout)` вызывают `collector.record_failure(METRIC_LLM_FALLBACK_RATE)`
  при наличии collector. `build_kernel(llm_client=..., live_metrics=...)` проводит
  collector в advisor-обёртки (no-op без collector).

## 3. Architecture
```
OpenAiCompatibleClient(ILlm)  --complete()-->  IHttpTransport.request()  [FAKE in tests]
        |                                  transport error -> LLMError / LLMTimeout
        v
adapter_for(ILlm) -> ILLMAdvisor  --advise()-->  kernel (LLMAdvisorReasoning/Planner)
                                            |  on LLMError/LLMTimeout:
                                            |    - graceful fallback == no-LLM result (I-10)
                                            |    - collector.record_failure(llm.fallback_rate)
```

## 4. Capstone proof (tests/test_llm_adapter_contract.py, K8)
- adapter удовлетворяет `ILlm` (fake transport): success -> `LlmResponse(actual_model)`.
- `adapter_for -> ILLMAdvisor -> LLMAdvice` (suggestion+confidence).
- transport error -> `LLMError` -> kernel fallback == результат БЕЗ LLM.
- timeout -> `LLMTimeout` -> kernel fallback == результат БЕЗ LLM.
- `llm.fallback_rate` инкрементируется на failure (3/3=1.0), 0.0 при успехе.
- Все тесты БЕЗ живой модели/сети — только fake `IHttpTransport`.

## 5. Relationship to O1 / K1 / K6 / K8 / I-10
- **O1**: adapter read-only advisor, НЕ мутирует HARD/FSM/контракты; kernel зависит
  только от портов (ILLMAdvisor/ILlm/IHttpTransport).
- **K1**: contracts/i_http.py + adapters/openai_compatible.py (stdlib-only в domain).
- **K6**: adapter зависит от IHttpTransport порта (не от provider SDK); kernel НЕ
  импортирует concrete adapter.
- **K8**: negative (error/timeout -> fallback == no-LLM) + O1 обязательно тестированы.
- **I-10**: kernel LLM-free по сути; concrete adapter доказывает bridge на реальном
  клиенте, не меняя core.

## 6. Constraints / Non-scope (per ТЗ)
- Живая модель/реальный network в CI — НЕТ (только fake transport). OmniRoute/Ollama
  адаптеры — future (один concrete adapter сейчас).
- RL/fine-tuning; SEARCH/RESEARCH/PLUGIN — отдельная волна.

## 7. Test Stability (honest note)
Детерминированно: fake transport возвращает предопределённый payload / бросает
typed error. `--count=5` не требуется. pre-existing warning (`\w` в
services/content_index.py:38) НЕ тронут (вне scope).

## 8. Future Work
- OmniRoute/Ollama concrete adapters поверх того же IHttpTransport (доказан bridge).
- Реальный telemetry export через ITelemetrySink (ТЗ-015) для llm.fallback_rate.
