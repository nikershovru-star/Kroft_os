---
id: ADR-075
title: "Federated orchestration — dispatch goal to remote trusted node via NW-01, real remote outcome updates trust (ТЗ-FED-ORCH-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [federated-orchestration, network, trust, orchestration, I-09, K1, K5, K6, K8, O1]
---

# ADR-075 — Federated orchestration (ТЗ-FED-ORCH-01)

## Context
ORCH-01 дал оркестрацию, но agent-dispatch в reference всегда `success=True` (Флаг 2 ORCH-01):
реальный исход придёт только с сетью, поэтому agent-trust монотонно растёт. NW-01 дал
`INetworkTransport` + trust-гейтинг (IDT-01). ТЗ-FED-ORCH-01 замыкает: оркестратор шлёт goal на
удалённый доверенный узел, тот исполняет локально своим оркестратором/плагином и возвращает
РЕАЛЬНЫЙ `TaskOutcome`; локальный оркестратор обновляет trust из реального исхода (success +,
failure -). Это реализует GitS Network Layer («сеть независимых узлов, обменивающихся
агентами/навыками») и ЗАКРЫВАЕТ Флаг 2 ORCH-01.

K5-разведка (commit 0) КРИТИЧНА: `INetworkTransport` (NW-01) — broadcast-only
(send_event/send_facts/send_soft_layer + on_event/on_facts), НЕТ request/response RPC для
goal-dispatch. ТЗ требует `dispatch_remote -> TaskOutcome` (request/response). Поэтому:
- НЕ дублируем `INetworkTransport` — создаём НОВЫЙ порт `IRemoteOrchestrator` (request/response
  dispatch), что K5-чисто (транспорт ≠ оркестрация, one-port-per-boundary).
- `INetworkTransport` переиспользуется КАК carrier: `send_facts(List[dict], node_id)` /
  `on_facts(handler)` несут `RemoteGoalRequest`/`RemoteOutcomeResponse` как dict-конверты по
  correlation-id (НЕ требуют CognitiveEvent). Второй транспорт НЕ создаётся.
- `ITrustRegistry.current_trust`/`record_outcome` (IDT-01) переиспользуются (НЕ дублируем).
- `ReferenceOrchestrator` (ORCH-01) расширяется (НЕ дублируем).

## Decision
- `contracts/i_federated_orchestrator.py`: `RemoteGoalRequest` / `RemoteOutcomeResponse` (frozen VO
  с `CausalMark` + `author_id`, урок Флага 1 LLM-01) + `IRemoteOrchestrator.dispatch_remote(node_id, goal)`.
- `kernel/federated_orchestrator.py`: `ReferenceRemoteOrchestrator` поверх `INetworkTransport` (carrier
  send_facts/on_facts) + `ITrustRegistry`. Trust-gating: `dispatch_remote` ТОЛЬКО если
  `current_trust(node) >= threshold` (current_trust = LATEST, НЕ `trust_score_of` MAX -> закрывает
  Флаг 1 IDT-01). После получения РЕАЛЬНОГО outcome -> `record_outcome(node, success, delta)` ->
  trust ЭВОЛЮЦИОНИРУЕТ из реального исхода; failure РЕАЛЬНО понижает (0.9->0.8 в тестах) ->
  ЗАКРЫВАЕТ Флаг 2 ORCH-01. `build_remote_orchestrator` фабрика (Флаг C, standalone).
- `kernel/orchestrator.py` (ORCH-01): `ReferenceOrchestrator` ОПЦИОНАЛЬНО принимает
  `IRemoteOrchestrator` + `remote_nodes` (procedural/remote = None по умолчанию -> обратная
  совместимость). `route()`: при отсутствии локального eligible -> fallback на доверенный remote-узел
  (current_trust >= threshold; детерминированный tie-break по node_id). `dispatch()`: kind='remote'
  -> `remote.dispatch_remote` (реальный outcome + trust-обновление внутри). Standalone (Флаг C).

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib; services/kernel -> contracts only.
- **O1**: trust-обновления SOFT (через ITrustRegistry); remote НЕ мутирует HARD/FSM локально.
- **I-09**: детерминизм — correlation по request_id; tie-break по node_id; FakeTransport синхронен.
- **Флаг C**: standalone фабрики (`build_remote_orchestrator`, `build_orchestrator`), НЕ в build_kernel.
- **K8 (negative)**: low-trust узел исключён; нет доверенного remote -> локальный routing цел (None).
- **К5**: НЕ дублирован INetworkTransport (carrier) / ITrustRegistry / ReferenceOrchestrator / IAgentPlatform.

## Consequences
- ✅ Флаг 2 ORCH-01 ЗАКРЫТ: реальный remote-outcome (failure) РЕАЛЬНО понижает trust узла -> петля
  доверия замкнута для федерации (как ORCH-01 замкнул её для локальных агентов/плагинов).
- ✅ GitS Network Layer: узлы обмениваются исполнением задач (goal -> remote -> outcome), НЕ только знаниями.
- ✅ K5: новый порт IRemoteOrchestrator (request/response) НЕ дублирует broadcast-транспорт; INetworkTransport
  переиспользован КАК carrier; ITrustRegistry/ReferenceOrchestrator переиспользованы.
- ✅ K1/K6: contracts + stdlib; kernel/services -> contracts only.
- ✅ O1: trust SOFT; remote не мутирует HARD/FSM.
- ✅ I-09: детерминизм (correlation + tie-break); FakeTransport детерминирован.
- ⚠️ Non-scope (future): multi-hop routing / discovery узлов (только прямой dispatch на известные узлы);
  LLM-backed remote исполнение; консенсус между узлами (только trust-gating IDT-01).

## Alternatives considered
- Эмулировать request/response поверх `send_event`/`on_event` (CognitiveEvent) -> ОТВЕРГНУТО: `send_event`
  типизирован под CognitiveEvent (нужен CausalMark-носитель), громоздко и ломает K1. `send_facts`
  несёт `List[dict]` + node_id — естественный carrier для dict-конвертов без новых типов.
- Встроить trust-gating/dispatch в `INetworkTransport` -> ОТВЕРГНУТО: смешивало бы транспорт и
  оркестрацию (нарушение one-port-per-boundary). Отдельный IRemoteOrchestrator чище.

## Evidence
- `tests/test_federated_orchestration.py`: 9 K8 тестов (remote real outcome; trust evolves from
  remote failure lowers / success raises; trust-gating excludes low-trust; orchestrator fallback to
  remote; low-trust-only -> None; determinism; no-remote local intact).
- Smoke: failure 0.9->0.8, success 0.8->0.9, low-trust excluded, fallback kind='remote'.
- Full suite GREEN, gate 14/14, akb-lint PASSED.
