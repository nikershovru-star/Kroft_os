---
id: ADR-079
title: "Real HTTP transport + local-model integration + graceful fallback (ТЗ-LLM-LIVE-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [llm, http-transport, local-model, fallback, IHttpTransport, K1, K5, K6, K8, O1, I-09]
---

# ADR-079 — Real HTTP transport + local-model integration + graceful fallback (ТЗ-LLM-LIVE-01)

## Context
LLM-02 (ADR-068) дал `OpenAiCompatibleClient` поверх порта `IHttpTransport`, но реальной
реализации транспорта НЕ было — в тестах использовался fake. ТЗ-LLM-LIVE-01 делает транспорт
НАСТОЯЩИМ: реальный HTTP-клиент за портом (без SDK провайдера в домене), направленный на
локальный OpenAI-совместимый эндпоинт (Ollama localhost:11434/v1 / LM Studio / vLLM). Fallback
(LLM-01) проверяется на РЕАЛЬНЫХ таймаутах/ошибках. Завершает «LLM = сменный инструмент»
реальным подключением.

K5-разведка (commit 0): `contracts/i_http.py` → `IHttpTransport` (порт ЕСТЬ) + `HttpResponse` +
`TransportError`/`TransportTimeout`. `adapters/openai_compatible.py` → `OpenAiCompatibleClient(ILlm)`
(LLM-02) зависит ТОЛЬКО от порта (K1/K6: НЕТ requests/httpx/urllib в домене), маппит
`TransportTimeout→LLMTimeout`, `TransportError→LLMError`. `contracts/i_llm_advisor.py` →
`ILLMAdvisor` + `adapter_for(ILlm)` → `advise()`; LLM-01 fallback (LLMError/LLMTimeout → kernel
retrieval-only) УЖЕ доказан `test_llm_advisor_fallback.py`. ЕДИНСТВЕННЫЙ реальный gap =
`HttpTransport(IHttpTransport)` (stdlib urllib, в adapters/). `model_platform.py`/`embedding.py`
бьют urllib НАПРЯМУЮ (legacy MVP), мимо порта — их НЕ переиспользуем и НЕ дублируем.

## Decision
- **НОВЫЙ порт НЕ нужен (K5):** переиспользуем `IHttpTransport` (ADR-068). commit 1 — docstring
  `i_http.py` уточнён (реальная реализация = `adapters/http_transport.py`).
- **Реальный транспорт (commit 2):** `adapters/http_transport.py` → `HttpTransport(IHttpTransport)`
  на stdlib `urllib.request` (НЕТ SDK — K6). Маппинг: `socket.timeout`/`urllib timeout` →
  `TransportTimeout`; `URLError`/`HTTPError`/`ConnectionError`/`OSError`/`ValueError` →
  `TransportError`. Возвращает `HttpResponse(status, body, headers)`; `timeout` из аргумента request.
- **Композиция (commit 3, Флаг C):** `composition/llm_client_factory.py` → `build_llm_client
  (base_url, model, api_key, timeout)` собирает `HttpTransport` + `OpenAiCompatibleClient` в готовый
  `ILlm`; `detect_local_ollama(host)` best-effort probe. K3/K6: единственная точка сборки конкретных
  адаптеров (`composition.* -> everything`); kernel импортирует только `ILLMAdvisor` + `adapter_for`
  (LLM-01), НЕ фабрику и НЕ provider SDK. НЕ в `build_kernel`.
- **Тесты K8 (commit 4, отдельно, Флаг 1b):** `tests/test_llm_live_transport.py` — 5 тестов против
  in-process `http.server` (НЕТ живой модели): реальный advise → LLMAdvice; HttpTransport имплементирует
  порт; server DOWN/TIMEOUT → LLMError/LLMTimeout → kernel fallback == retrieval-only; K6 domain-без-SDK (AST).
- **Docs (commit 5):** ADR-079 + AKB + CHANGELOG + PROJECT_STATUS.

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: домен (contracts/kernel) НЕ импортирует requests/httpx/openai; HttpTransport в adapters/;
  build_llm_client в composition/.
- **O1**: LLM — советник; fallback защищает (LLM-01); trust/ядерные инварианты НЕ зависят от LLM.
- **I-09**: тесты детерминированы (in-process HTTP-сервер); реальный эндпоинт опционален.
- **Флаг C**: standalone фабрика, НЕ в build_kernel. **K5**: НЕ дублирован порт.

## Consequences
- ✅ LLM-LIVE-01 DONE: транспорт НАСТОЯЩИЙ (stdlib urllib, K6-clean); `OpenAiCompatibleClient`
  говорит с реальным OpenAI-совместимым эндпоинтом (Ollama/LM Studio/vLLM) поверх порта.
- ✅ Fallback валидирован на РЕАЛЬНЫХ таймаутах/ошибках (down-порт + handler-sleep > client-timeout):
  network failure → TransportError/TransportTimeout → LLMError/LLMTimeout → kernel retrieval-only
  (== no-LLM результату), без краша.
- ✅ K5: НОВЫЙ порт НЕ создан (IHttpTransport reused). K1/K6: domain без SDK; HttpTransport в adapters/;
  build_llm_client в composition/. K8: AST-проверка отсутствия SDK в домене.
- ✅ LLM-01/02 тесты НЕ сломаны (обратно-совместимо: добавлен только transport).
- ⚠️ Non-scope (future): мульти-провайдер роутинг (OmniRoute) — отдельный слой; RL/fine-tuning;
  обязательная живая модель в CI (тесты на in-process сервере, Ollama опционален).

## Alternatives considered
- Расширить `model_platform.py` (прямой urllib) до порта — ОТВЕРГНУТО: нарушало бы K6 (direct SDK в
  адаптере вместо порта) и дублировало `OpenAiCompatibleClient` (LLM-02). Создан ЧИСТЫЙ транспорт за портом.
- Использовать `requests`/`httpx` — ОТВЕРГНУТО: внешняя зависимость в домене (K6); stdlib urllib достаточно
  для OpenAI-совместимого JSON over HTTP.

## Evidence
- `tests/test_llm_live_transport.py`: 5 K8 тестов (real HTTP advise; port impl; down/timeout fallback;
  K6 no-SDK-in-domain AST).
- Smoke: `build_llm_client('http://localhost:11434/v1')` собирается; `detect_local_ollama()` вернул
  True (Ollama запущен локально — совместимо с ранее зафиксированным окружением RTX 3060 + Ollama).
- Full suite GREEN, gate 14/14, akb-lint PASSED.
