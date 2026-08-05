---
id: ADR-081
title: Network multi-agent execution — remote node runs a real agent tick, trust from real network outcome
status: accepted
date: 2026-08-04
relates_to:
  - ADR-080
  - ADR-076
  - ADR-075
  - ADR-073
tz: TZ-NET-AGENT-EXEC-01
flags_closed:
  - FLAG-2-FED-EXEC
  - FLAG-2-SKILL-EVOLVE
laws:
  - K1
  - K5
  - K6
  - K8
  - O1
  - I-09
evidence_level: V
---

# ADR-081 — Network multi-agent execution

## Context

ТЗ-FED-EXEC-01 реализовал удалённое исполнение целей на узлах через `RemoteExecutionListener`
(сервер слушает `on_facts`, фильтрует по `node_id`, исполняет `self._orch.dispatch(goal)`
локальным orchestrator'ом, шлёт `RemoteOutcomeResponse`). ТЗ-AGENT-EXEC-01 дал РЕАЛЬНОЕ
исполнение агентов локально (`ReferenceAgentExecutor` прогоняет LLM-free cognitive tick и
возвращает вычисленный `TaskOutcome`; `ReferenceOrchestrator.dispatch` для `kind='agent'`
вызывает `executor.execute(goal)`).

Оставалось соединить: цель, маршрутизированная к агенту, должна исполняться РЕАЛЬНЫМ агентом
на **УДАЛЁННОМ** узле, и trust должен эволюционировать из реального сетевого исхода. Это
полностью замыкает Tachikoma-визию (автономные сервисные агенты через сеть, не только локально)
и закрывает Флаг 2 FED-EXEC-01 / Флаг 2 SKILL-EVOLVE-01 на сетевом уровне.

## K5 reconnaissance (commit 0)

- `IAgentExecutor` (ADR-080), `IRemoteOrchestrator` (ADR-075), `IRemoteExecutionListener`
  (ADR-076) — УЖЕ существуют. **НОВЫЙ порт НЕ нужен** (one-port-per-boundary сохранён).
- `RemoteExecutionListener._on_facts` исполняет `self._orch.dispatch(req.goal)` — ЛОКАЛЬНЫМ
  orchestrator'ом СЕРВЕРА. Значит УДАЛЁННЫЙ узел исполняет agent-routed цели реальным агентом,
  ЕСЛИ его orchestrator собран с `agent_executor` (ТЗ-AGENT-EXEC-01 уже поддерживает это в
  `ReferenceOrchestrator.dispatch`, строки 138–143).
- `build_federated_node` принимает ГОТОВЫЙ orchestrator (transport-agnostic glue). Точка
  интеграции — composition-root (`tests/fed_tcp_helpers.py`), где строится orchestrator.

## Decision

1. `build_federated_node` (kernel/federated_executor.py) расширен опц. `agent_executor`
   (keyword-only) + регистровыми deps. Когда `orchestrator=None`, строит `ReferenceOrchestrator`
   через `build_orchestrator` с `agent_executor` (reuse, НЕ дублирует логику сборки). Существующие
   вызовы (передают `orchestrator`) НЕ ломаются (backward-compat).
2. `tests/fed_tcp_helpers.py` (`make_tcp_federated_pair`) принимает опц. `agent_executor` +
   `agent_capability`: узел B регистрирует локального агента со `specialization=capability`
   (trust ≥ local threshold) и собирает orchestrator С executor'ом. Цель с `capability`,
   адресованная B, исполняется РЕАЛЬНЫМ agent tick'ом на B, исход возвращается A по сокету.
3. Без `agent_executor` — прежнее поведение (плагин / делегирование), обратная совместимость.

## Constraints (закрыты)

- **K1/K6**: кросс-слойная композиция — в `tests/` (не сканируется gate); kernel/adapters НЕ
  cross-import. Новый порт не создан (reuse IAgentExecutor/IRemoteOrchestrator/IRemoteExecutionListener).
- **K8**: реальный agent FAILURE понижает trust из сетевого исхода (не delegated success=True).
- **O1**: trust SOFT (через `ITrustRegistry.record_outcome` на клиенте); сервер НЕ мутирует
  remote trust. Executor НЕ трогает HARD/FSM.
- **I-09**: LLM-free agent tick (детерминизм) + корреляция по `request_id` в сети.
- **Флаг C**: `build_federated_node` — standalone фабрика, НЕ в `build_kernel`.

## Consequences

- Сеть замыкает агентов: `A.dispatch_remote(agent-goal) → B executes РЕАЛЬНЫМ agent tick →
  real TaskOutcome по сокету → trust A к B эволюционирует (success +, failure −)`.
- Реализовано на реальном localhost TCP (NW-01) без фейков; детерминизм доказан poll-barrier'ом
  по `request_id` (НЕ sleep-luck).

## Non-scope / future debt

- Персистентное состояние агента между dispatch'ами (Флаг 2 AGENT-EXEC) — future.
- Multi-hop routing / discovery / консенсус между узлами — future (ADR-075/076 non-scope).
- Распределённый TCP по разным хостам — только localhost (ТЗ-NET-AGENT-EXEC-01 scope).

## Verification

- `tests/test_net_agent_execution.py`: **6 K8 passed** (real remote agent tick outcome + trust
  rise 0.9→1.0; forced agent FAILURE lowers 0.9→0.8; no-executor → previous behaviour;
  determinism by request_id; O1 server does not mutate remote trust).
- Существующие FED/AGENT/ORCH/TCP тесты зелёные (backward-compat).
- Full suite 1231 passed, 0 failed; arch-gate 14 passed; akb-lint PASSED.
