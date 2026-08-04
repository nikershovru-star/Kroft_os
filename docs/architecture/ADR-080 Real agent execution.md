---
id: ADR-080
title: "Real agent execution: agent-routed dispatch runs a real cognitive tick (ТЗ-AGENT-EXEC-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [agent-execution, orchestrator, cognitive-kernel, trust-evolution, IAgentExecutor, K1, K5, K6, K8, O1, I-09]
---

# ADR-080 — Real agent execution (ТЗ-AGENT-EXEC-01)

## Context
ORCH-01 / FED-EXEC: когда оркестратор маршрутизирует goal к агенту (`kind='agent'`), `dispatch`
возвращал `TaskOutcome(success=True, 'agent delegated')` и ВСЕГДА поднимал trust через
`record_outcome(chosen_id, True)` — реального исхода не было (Флаг 2 FED-EXEC-01, Флаг 2
SKILL-EVOLVE-01: агентский путь `_execute_skill`). Это последний «фейк» в оркестрации.

ТЗ-AGENT-EXEC-01 делает исполнение агента НАСТОЯЩИМ: агент реально прогоняет когнитивный tick
(`build_kernel`: perceive→reason→plan→decide→execute) на цели и возвращает ВЫЧИСЛЕННЫЙ `TaskOutcome`,
из которого эволюционирует trust (success +, failure -). Завершает «Tachikoma»-визию (автономные
сервисные агенты) и замыкает петлю доверия для агентов (как FED-EXEC замкнул её для плагинов/узлов).

K5-разведка (commit 0): `orchestrator.py:131-134` — delegated success=True баг. `route()` строит
`kind='agent'` из `IIdentityRegistry` (агенты со specialization/permissions/trust), скоринг spec+trust (I-09).
`build_kernel(name)+attach_executor(ReferenceExecutor())+tick(intent)->._last_selected_plan` — РЕАЛЬНЫЙ
LLM-free tick (детерминирован, I-09). `IAgentPlatform.run(goal:str)->AgentResult` (ADR-014) существует,
но это ДРУГОЙ boundary (возвращает AgentResult для строковой цели) — НЕ переиспользуем, создаём НОВЫЙ
порт `IAgentExecutor.execute(goal:OrchestrationGoal)->TaskOutcome` (one-port-per-boundary, единообразно
с plugin/remote/skill в orchestrator).

## Decision
- **НОВЫЙ порт (commit 1):** `contracts/i_agent_executor.py` — `IAgentExecutor.execute(goal)->TaskOutcome`
  (+ опц `can_execute`). K5 one-port-per-boundary: НЕ дублирует `IAgentPlatform` (ADR-014) — тот координирует
  платформу целиком и возвращает `AgentResult`; здесь граница уже (goal-shape + result-shape = TaskOutcome,
  как у остальных executor-видов). O1: executor НЕ мутирует HARD/FSM, только outcome; trust эволюционирует
  CALLER (orchestrator) через `record_outcome` (SOFT). I-09: reference impl LLM-free tick (детерминизм).
- **Reference impl (commit 2):** `kernel/agent_executor.py` — `ReferenceAgentExecutor(IAgentExecutor)`
  транслирует goal→Intent, прогоняет `build_kernel` tick, возвращает РЕАЛЬНЫЙ `TaskOutcome` (plan выбран/
  исполнен = success). НЕ поднимает исключений: любой сбой → `TaskOutcome(success=False)` (чтобы trust
  ПОНИЖАЛСЯ, как при реальном провале). `build_agent_executor` (Флаг C, НЕ в build_kernel). K1/K6: kernel/*
  → contracts + stdlib, НЕТ adapters/services imports.
- **Интеграция (commit 3, НЕ break):** `ReferenceOrchestrator` принимает опц `agent_executor`; `dispatch()`
  `kind='agent'` ВЫЗЫВАЕТ `executor.execute(goal)` → РЕАЛЬНЫЙ outcome → `record_outcome` (trust эволюционирует
  из реального исхода). БЕЗ executor → прежнее делегированное поведение СОХРАНЕНО (обратная совместимость).
  `build_orchestrator` пробрасывает `agent_executor`. Закрывает Флаг 2 FED-EXEC-01 + Флаг 2 SKILL-EVOLVE-01.
- **Тесты K8 (commit 4, отдельно, Флаг 1b):** `tests/test_agent_execution.py` — 5 тестов: real agent outcome
  из kernel tick + trust rises (0.9->1.0); real FAILURE lowers trust (0.9->0.8); no-executor → delegated
  (backward-compat); determinism (I-09, LLM-free); O1 SOFT (no HARD/FSM mutation).
- **Docs (commit 5):** ADR-080 + AKB + CHANGELOG + PROJECT_STATUS.

## Consequences
- ✅ Флаг 2 FED-EXEC-01 ЗАКРЫТ: agent-routed dispatch возвращает РЕАЛЬНЫЙ outcome из kernel tick; trust
  эволюционирует из реального исхода (success +, failure -), как для плагинов/узлов.
- ✅ Флаг 2 SKILL-EVOLVE-01 ЗАКРЫТ: агентский путь `_execute_skill` теперь при ведомом executor'е даёт
  реальный исход (до этого возвращал True делегированно).
- ✅ K5: НОВЫЙ порт `IAgentExecutor` не дублирует `IAgentPlatform` (one-port-per-boundary).
- ✅ O1/K6: executor НЕ мутирует HARD/FSM; trust SOFT; kernel/* → contracts+stdlib (gate-compliant).
- ✅ Обратная совместимость: без `agent_executor` поведение идентично pre-ТЗ (delegated success=True).
- ✅ «Tachikoma»-визия: автономные сервисные агенты реально исполняют цели локально.
- ⚠️ Non-scope (future): реальное мульти-агент исполнение ПО СЕТИ для агентов (remote agent exec через
  FED-EXEC) — опционально далее; здесь локальный agent executor. RL/сложное планирование; LLM-backed agent
  (LLM опционален через build_kernel llm_client, ядро LLM-free).

## Alternatives considered
- Переиспользовать `IAgentPlatform.run` и маппить `AgentResult->TaskOutcome` — ОТВЕРГНУТО: ломает
  one-port-per-boundary и требует lossy-маппинга на каждом вызове; orchestrator uniform над TaskOutcome.
- Сделать agent dispatch всегда success=True (как раньше) — ОТВЕРГНУТО: это и есть закрываемый Флаг 2
  (trust никогда не падал бы при реальном провале агента).

## Evidence
- `tests/test_agent_execution.py`: 5 K8 тестов (real tick outcome + trust rise; real failure lowers trust;
  no-executor delegated; determinism; O1 SOFT).
- Smoke: `dispatch(kind='agent')` с executor → `TaskOutcome(success=True)`, trust 0.9→1.0; без executor →
  delegated `success=True` (compat).
- Full suite GREEN, gate 14/14, akb-lint PASSED.
