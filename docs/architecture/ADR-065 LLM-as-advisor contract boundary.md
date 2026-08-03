---
id: ADR-065
title: "LLM-as-advisor plug-in + graceful fallback (ТЗ-LLM-01) — validation of contract-boundary (I-10, kernel purity)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.85
confidence: high
risk: low
related: [ADR-054, ADR-060, ADR-062, ADR-063, ADR-064, TZ-015, ME-01, EX-01, SE-01, I-10, I-03]
addresses: [TЗ-LLM-01, O1, K1, K6, K8]
---

## 1. Context
Все когнитивные контуры (Foundation → … → SE-01) построены на детерминированных
reference-имплах и НИ РАЗУ не использовали LLM. Центральный тезис архитектуры:
«LLM — сменный СОВЕТНИК за контрактной границей; ядро работает без модели»
(I-10, kernel purity). До ТЗ-LLM-01 это было ДЕКЛАРАЦИЕЙ, не проверенным свойством:
fallback-поведение при сбое модели не было доказано кодом.

ТЗ-LLM-01 доказывает тезис кодом: advisor втыкается через порт, влияет на ranking,
но Decision детерминирован; при исключении/таймауте LLM ядро gracefully fallback на
reference (результат == без LLM); без LLM всё неизменно. Не требует живой модели.

## 2. Decision
- **Контракт (K1, contracts/i_llm_advisor.py):** `ILLMAdvisor` (порт) + `LLMAdvice`
  (frozen VO) + `LLMError`/`LLMTimeout` + `AdviseContext`. `adapter_for(ILlm)` мостит
  существующий Model Platform порт `contracts/i_llm.ILlm` в advisor (НЕ дублирует порт —
  KROFT «one port per boundary»). Ядро зависит только от `ILLMAdvisor`.
- **Reference impl (LLM-free core сохранён; kernel/llm_advisor.py):**
  - `MockLLMClient(ILLMAdvisor)`: детерминированный rule-based advisor (no real model);
    `fail=True` -> `LLMError` (graceful-fallback path).
  - `LLMAdvisorReasoning(KnowledgeAwareReasoning)`: `reason()` добавляет boosted
    `ReasoningStep` из `advisor.advise()`; при `LLMError`/`LLMTimeout` -> graceful
    fallback на чистый reference (steps unchanged).
  - `LLMAdvisorPlanner(ReferencePlanner)`: `plan()` ре-ранжирует кандидатов через
    advisor (boosted Plan на фронт); при сбое -> `super().plan()` (чистый reference
    result). LLM НЕ делает финальный выбор (I-03).
- **Интеграция (build_kernel):** `build_kernel(node_id, clock, llm_client=None)`.
  `llm_client` опционален: `ILlm` model-port (через `adapter_for`) ИЛИ `ILLMAdvisor`.
  reasoning/planner используют advisor-обёртки. БЕЗ client: `advisor=None` ->
  обёртки деградируют до PURE reference (поведение идентично LLM-free build).

## 3. Architecture (contract boundary)
```
[ILlm / ILLMAdvisor] --advise()--> LLMAdvice (suggestion + confidence)
        |                                      |
        v                                      v
LLMAdvisorReasoning/Planner  --boosted step/plan-->  candidate re-rank
        |                                      |
        v                                      v
            ReferenceReasoning/Planner (unchanged fallback path)
                        |
                        v
                DeterministicDecisionEngine.select (FINAL pick, I-03)
```
LLM НИКОГДА не выбирает финал. При сбое: `LLMError`/`LLMTimeout` -> обёртки возвращают
чистый reference result == результату без LLM.

## 4. Capstone proof (tests/test_llm_advisor_fallback.py, 7 passed)
- advice меняет RANKING (boosted candidate -> фронт), но Decision (не LLM) выбирает.
- `LLMError` -> graceful fallback == результат без LLM (kernel не крашит).
- `LLMTimeout` -> graceful fallback == результат без LLM.
- без LLM ядро неизменно (`build_kernel()` == `build_kernel(llm_client=None)`).
- LLM НИКОГДА не делает финальный выбор; advisor read-only (O1: нет select/mutate).
- K6: kernel зависит только от `ILLMAdvisor` порта; `adapter_for` мостит `ILlm`.

Интеграционный капстоун: `build_kernel()` и `build_kernel(llm_client=MockLLMClient(fail=True))`
дают ОДИНАКОВЫЙ `selected_plan.steps` — доказывает kernel LLM-free по сути, не по
декларации.

## 5. Relationship to O1 / K1 / K6 / K8 / I-10
- **O1:** advisor read-only, НЕ мутирует HARD/FSM/контракты.
- **K1:** contracts+stdlib; advisor-слой в contracts/i_llm_advisor.py.
- **K6:** kernel зависит только от порта `ILLMAdvisor`; конкретный `ILlm` adapter —
  вне ядра (services/adapters).
- **K8:** negative-поведение (exception/timeout -> fallback == no-LLM) обязательно
  тестируется, не предполагается.
- **I-10 (kernel purity):** ТЕПЕРЬ ПРОВЕРЕНО КОДОМ, а не декларацией.

## 6. Constraints / Non-scope
- Живая LLM-интеграция (реальные API) — только детерминированный mock-adapter.
- RL / fine-tuning. Multi-agent оркестрация (ТЗ-AGENT закрыт) — не переоткрывать.
- Не дублировать порт: `i_llm_advisor.py` мостит `i_llm.ILlm`, не форкает его.

## 7. Test Stability (honest note)
Тесты K8 детерминированы, не требуют сети/таймингов. MockLLMClient + monkeypatch
reference `plan()` — воспроизводимо. `--count=5` не требовался.

## 8. Future Work
- Реальные LLM-адаптеры (OpenAI/Ollama/OmniRoute) через `adapter_for(ILlm)` — без
  изменения ядра (порт уже готов).
- Confidence-калибровка advisor (сейчас фиксирован 0.7/boost +0.3).
- Substring-matching политик и фиксированный recall-boost (ADR-064 §8) — задок-долг.
