---
id: ADR-073
title: "Trust-aware orchestration — route goal to best agent/plugin, evolve trust from outcome (ТЗ-ORCH-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [orchestration, trust, identity, plugins, multi-agent, I-09, K1, K6, K8, O1]
---

# ADR-073 — Trust-aware orchestration (ТЗ-ORCH-01)

## Context
IDT-01 дал Identity (specialization/trust/permissions) + Trust + ActionLog; PLUGIN-01 — реестр
capabilities. Но они НЕ использовались для поведения. ТЗ-ORCH-01 («Section 9» визии) — оркестратор
маршрутизирует задачу к лучшему исполнителю (агент из IIdentityRegistry ИЛИ плагин из
IPluginRegistry) по specialization-match + trust_level + permissions, исполняет, логирует в
IActionLog и обновляет trust из исхода (успех повышает, провал понижает) — trust эволюционирует,
замыкая петлю. Это превращает построенные слои в поведение.

K5-разведка (commit 0): trust-aware ROUTING НЕ существовал. Смежные порты УЖЕ есть и
переиспользуются, НЕ дублируются: `IIdentityRegistry`/`ITrustRegistry`/`IActionLog` (IDT-01),
`IPluginRegistry` (PLUGIN-01). `IAgentPlatform` (ТЗ-AGENT-001) — это agent-platform
(execute/run/ask), НЕ оркестратор -> НЕ дублируем (реальное мульти-агент исполнение через сеть
-> future, NW-01). `ITrustRegistry` расширен (record_outcome/current_trust/seed) для эволюции
trust из исхода; `trust_score_of` (MAX) НЕ тронут (FSE-01 gating цел) -> закрывает Флаг 1 IDT-01.

## Decision
- `contracts/i_orchestrator.py`: `OrchestrationGoal` (frozen VO: goal_id, capability,
  required_permission, payload), `RoutingDecision` (frozen VO: chosen_id, kind, rationale, score),
  `TaskOutcome` (frozen VO: success, detail), `IOrchestrator` (route/dispatch).
- `kernel/orchestrator.py`: `ReferenceOrchestrator` over IIdentityRegistry + IPluginRegistry +
  ITrustRegistry + IActionLog. score = specialization_match * trust; permission-violating /
  low-trust (< threshold) ИСКЛЮЧАЮТСЯ; max score + детерминированный тай-брейкер по id.
  dispatch: invoke plugin (real) / delegate agent (logged); log в IActionLog; update trust из
  исхода (success +delta, failure -delta) через ITrustRegistry.record_outcome. `build_orchestrator`
  фабрика — standalone (Флаг C), НЕ в build_kernel.

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib only; orchestrator импортирует только contracts.
- **O1**: orchestrator НЕ мутирует HARD/FSM; trust-обновления — SOFT (через ITrustRegistry).
- **I-09**: scoring + тай-брейкер по id детерминированы.
- **Флаг C**: standalone фабрика, НЕ в build_kernel (god-factory не усугубляется).
- **K8 (negative)**: нет eligible -> route None / dispatch TaskOutcome(False); unknown -> None.
- **Фокус**: trust ЭВОЛЮЦИОНИРУЕТ из исхода (dispatch -> log -> trust update).

Trust-модель (orchestrator читает `current_trust` = LATEST, НЕ `trust_score_of` = MAX):
- сидирование: `seed(agent_id, agent.trust_level)` при build (idempotent).
- success -> +delta (cap 1.0); failure -> -delta (floor 0.0). Закрывает Флаг 1 IDT-01
  (trust-then-attack): один высокий item НЕ делает автора перманентно доверенным.

## Consequences
- ✅ Построенные слои (Identity/Trust/Plugins) стали ПОВЕДЕНИЕМ: маршрутизация + эволюция trust.
- ✅ Петля замкнута: dispatch -> log -> trust update -> следующий route учитывает обновлённый trust.
- ✅ K5: переиспользованы IDT/PLUGIN порты + TrustMeta; IAgentPlatform НЕ дублирован.
- ✅ K1/K6: contracts + stdlib; kernel -> contracts only.
- ✅ O1: реестры read/write-only своё состояние; HARD/FSM не тронуты.
- ✅ K8: negative тесты (no eligible, low-trust, permission).
- ⚠️ Non-scope (future): реальное мульти-агент исполнение через сеть (NW-01) — reference делегирует
  агента и логирует исход, НЕ вызывает IAgentPlatform.execute; RL/сложное планирование распределения
  — только детерминированный scoring.

## Alternatives considered
- Встроить trust-routing в IAgentPlatform (AGENT-001) -> ОТВЕРГНУТО: смешивало бы agent-platform
  с orchestration; нарушило бы one-port-per-boundary. Отдельный IOrchestrator + переиспользование
  портов — чище.
- Маршрутизировать по `trust_score_of` (MAX) -> ОТВЕРГНУТО: Флаг 1 IDT-01 (trust-then-attack);
  выбран `current_trust` (LATEST, эволюционирует).

## Evidence
- `tests/test_orchestrator.py`: 8 K8 тестов (route by spec+trust, permission/low-trust exclusion,
  trust evolves from outcome, negative, determinism).
- Smoke: agent trust 0.9->1.0 (success), plugin 0.5->0.6 (success), failure lowers.
- Full suite GREEN, gate 14/14, akb-lint PASSED.
