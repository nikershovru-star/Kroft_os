---
id: ADR-063
title: "Execution Layer + Real Outcome-Feedback — replacing the outcome-proxy (ТЗ-EX-01)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.84
confidence: high
risk: low
related: [ADR-054, ADR-060, ADR-062, TZ-015, RF-01, EX-01, I-10]
addresses: [TZ-EX-01, RF-01-FLAG2, O1]
---

## 1. Context
RF-01 (ТЗ-RF-01) замкнул когнитивный цикл reflection, но питается **PROXY**-исходом:
`success = bool(decision.selected_plan_id)` (почти всегда true), `utility = confidence`
решения. Это не обучение из среды — Self-Evolving был почти вакуумным. RT-01 замкнул
runtime-петлю, но когнитивная эволюция всё ещё ела прокси-сигнал.

ТЗ-EX-01 строит **EXECUTION-слой**: система ИСПОЛНЯЕТ выбранное решение в среде и
снимает НАСТОЯЩИЙ результат (success/failure, observation, reward). Этот реальный
исход заменяет proxy и кормит Reflection (RF-01) честным сигналом. Закрывает
**ФЛАГ 2 RF-01** (outcome-proxy).

## 2. Decision
- **Контракты (K1, contracts/i_execution.py):**
  - `ExecutionResult` (frozen VO): `action_id / success / observation / reward /
    confidence / causal / provenance` — СЫРОЙ ответ среды.
  - `IExecutionEnvironment.step(action) -> ExecutionResult` (среда).
  - `IExecutor.execute(action, timeout) -> ExecutionResult` (маршрутизация).
  - `IActionAdapter` (опц.): маппинг `action.kind` -> backend (Kernel Purity, ADR-028).
- **Разделение Result / Outcome (критично, НЕ путать):**
  - `ExecutionResult` = raw ответ среды (среда его производит).
  - `ExecutionOutcome` (уже в cognitive_domain, RF-01) = сигнал для Reflection;
    **СТРОИТСЯ ИЗ** `ExecutionResult` (`success <- result.success`, `utility <-
    result.reward`). Reflection видит Outcome, не сырую среду.
- **Reference impl (LLM-free, I-09):** `kernel/execution.py`:
  - `ReferenceExecutionEnvironment.step`: deterministic rule-map (payload
    `choose_blue` -> success/0.9; `choose_red` -> fail/0.1; unknown -> fail/0.0).
  - `ReferenceExecutor.execute`: маршрутизирует Action в среду по kind (IActionAdapter
    опц. для реальных backend-ов позже). Без wall-clock sleep (синхронный, deterministic).
- **Интеграция (kernel Execute-фаза):**
  - `attach_executor(executor)`: wire реального backend; `None` -> proxy fallback.
  - Execute-фаза: при executor выбранный Plan -> `Action(kind="execute_plan",
    payload=steps)` -> `executor.execute` -> `ExecutionResult` -> РЕАЛЬНЫЙ
    `ExecutionOutcome`. Без executor — **proxy fallback** (decision accepted /
    confidence), backward compat (не ломает RF-01/NW-01/RT-01 тесты).
- **O1 Self-Evolving guard:** Execute НЕ мутирует HARD-слой / FSM-инварианты /
  контракты / структуру ядра. Executor возвращает только `ExecutionResult`; он не
  имеет поверхности мутации kernel/HARD (проверено в тестах).

## 3. Architecture (execution + feedback loop)
```
kernel.tick():
  ...
  Execute-phase:
    if self._executor is not None:
        action = Action(kind="execute_plan", payload="\n".join(plan.steps))
        result = self._executor.execute(action)          # REAL environment
        outcome = ExecutionOutcome(success=result.success, utility=result.reward, ...)
    else:
        outcome = ExecutionOutcome(success=decision accepted, utility=confidence)  # proxy
  self._outcomes.append(outcome)
  -> Reflection (RF-01) uses REAL outcome -> consolidation/deprecation
```

## 4. Relationship to RF-01 / RT-01 / O1
- **RF-01 ФЛАГ 2 ЗАКРЫТ:** эволюция питается настоящим исходом среды, не proxy.
  Repeated real failures (`success=False`) -> RF-01 deprecation (evidence:
  `test_repeated_real_failures_drive_rf01_deprecation`).
- **RT-01 (runtime):** тюнингует SOFT параметры; EX-01 (execution) исполняет решения.
  Разные петли, но обе делают Self-Evolving неподдельным (операционно + когнитивно).
- **O1:** execution mutation surface = NONE for HARD/FSM/contracts.

## 5. Constraints / Non-scope
- K1/K6/K8 соблюдены (contracts + stdlib; services→adapters через порты).
- Реальные LLM/agent-адаптеры как executor — НЕ в scope (только deterministic reference).
- Полная multi-agent оркестрация (ТЗ-AGENT закрыт) — НЕ переоткрывать.
- RL / reward-learning — reference reward только как сигнал исхода.

## 6. Test Stability (honest note)
Тесты K8 (tests/test_execution_feedback.py, 9 passed) детерминированы, не требуют сети/
таймингов. Rule-map среды воспроизводим. `--count=5` не требовался.

## 7. Future Work
- Реальные execution backend-ы (LLM/agent/tool адаптеры) через `IActionAdapter` при
  стабилизации контрактов.
- Подключить real outcome к RT-01 runtime-метрикам (delivery success из реального
  исполнения, а не из federation) — замкнуть обе петли на настоящей среде.
