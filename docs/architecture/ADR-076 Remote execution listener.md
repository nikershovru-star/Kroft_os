---
id: ADR-076
title: "Remote execution listener — node-server executes goal locally, returns real TaskOutcome (ТЗ-FED-EXEC-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [federated-execution, network, trust, orchestration, I-09, K1, K5, K6, K8, O1]
---

# ADR-076 — Remote execution listener (ТЗ-FED-EXEC-01)

## Context
FED-ORCH-01 дал КЛИЕНТСКУЮ сторону (dispatch_remote + trust-эволюция из remote-исхода), но
responder был фейковым (`FakeTransport` в тестах — заранее заданный outcome). ТЗ-FED-EXEC-01
добавляет СЕРВЕРНУЮ половину: узел-слушатель принимает `RemoteGoalRequest`, исполняет его СВОИМ
локальным `ReferenceOrchestrator`/плагином и возвращает РЕАЛЬНЫЙ `TaskOutcome`. Capstone становится
настоящим: два узла обмениваются исполнением без фейков; trust обновляется из реально вычисленного
исхода. Завершает GitS Network Layer (Tachikoma: автономные сервисные агенты на узлах).

K5-разведка (commit 0) КРИТИЧНА:
- `INetworkTransport` (NW-01) — broadcast-only carrier (send_facts/on_facts) -> переиспользуется,
  НЕ дублируется.
- FED-ORCH-01 `ReferenceRemoteOrchestrator` (client): его wire-helpers были ПРИВАТНЫ
  (`_request_to_dict` и т.д.) в `kernel/federated_orchestrator.py`. Чтобы сервер НЕ дублировал
  формат -> wire-формат ЦЕНТРАЛИЗОВАН в `contracts/i_federated_orchestrator.py` (commit 1):
  `REQ_MARKER`/`RESP_MARKER` + `encode_goal_request`/`decode_goal_request`/`encode_outcome_response`/
  `decode_outcome_response`/`is_goal_request`/`is_outcome_response`. Client отрефакторен на них
  (behaviour-preserving, доказано FED-ORCH-01 тестами 9/9). K5 single-source-of-truth.
- `IRemoteOrchestrator` (client) НЕ дублируется — НОВЫЙ порт `IRemoteExecutionListener` = СЕРВЕР
  (one-port-per-boundary: client ≠ server).
- `ReferenceOrchestrator` (ORCH-01) переиспользуется для локального исполнения (реальный outcome).
- `ITrustRegistry` (IDT-01): trust ЭВОЛЮЦИОНИРУЕТ на КЛИЕНТЕ из реального исхода (server НЕ мутирует
  remote trust -> O1).

## Decision
- `contracts/i_federated_orchestrator.py` (commit 1, расширение FED-ORCH-01):
  - Централизован wire-формат (single-source-of-truth) + `IRemoteExecutionListener` (server):
    `start()`/`stop()`; слушает входящие goal-requests, фильтрует по `node_id` (только свои),
    исполняет локальным `IOrchestrator.dispatch(goal)`, шлёт `RemoteOutcomeResponse`.
- `kernel/federated_executor.py` (commit 2): `ReferenceRemoteExecutionListener` (implements
  `IRemoteExecutionListener`) поверх `INetworkTransport` (carrier send_facts/on_facts) +
  `IOrchestrator` (локальное исполнение). `build_remote_execution_listener` фабрика (Флаг C).
- `kernel/federated_executor.py` (commit 3): `build_federated_node` + `FederatedNode` (integration,
  Флаг C, standalone, НЕ в build_kernel): узел = КЛИЕНТ (build_remote_orchestrator) + СЕРВЕР
  (build_remote_execution_listener), делят ОДИН локальный orchestrator + ОДИН trust + ОДИН transport.
  Два in-process узла диспетчеризуют друг на друга через `SyncTransport` (in тестах; real TCP NW-01
  опционален, как в FSE-01).

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib; services/kernel -> contracts only.
- **O1**: trust-обновления SOFT; СЕРВЕР НЕ мутирует remote trust (клиент обновляет из исхода);
  HARD/FSM не трогаются (только локальный plugin).
- **I-09**: детерминизм — correlation по request_id; `SyncTransport` синхронен в тестах.
- **Флаг C**: standalone фабрики (build_remote_execution_listener, build_federated_node), НЕ в build_kernel.
- **K8 (negative)**: запрос НЕ на этот узел -> игнор (фильтр по node_id); low-trust узел исключён клиентом.
- **К5**: НЕ дублирован INetworkTransport (carrier) / IRemoteOrchestrator (client) / ReferenceOrchestrator
  (ORCH-01, переиспользован для локального исполнения).

РЕАЛЬНЫЙ БАГ интеграции (найден и исправлен в commit 4): node = client + server на ОДНОМ transport
оба вызывают `on_facts` -> перезапись слота (последний побеждает) -> один handler терялся, ответ
не доходил до клиента. Тестовый `SyncTransport`/`_SyncNetwork` теперь FAN-OUT (node_id -> list
  [handler]) -> оба (client+server) получают facts. Аналогично для real TCP NW-01 (опц. тесты).

## Consequences
- ✅ Capstone настоящий: два узла (A, B) обмениваются исполнением БЕЗ фейков — B исполняет goal
  СВОИМ локальным плагином, возвращает реальный outcome; A обновляет trust из него.
- ✅ Флаг 2 ORCH-01 ЗАКРЫТ на сетевом уровне: failure РЕАЛЬНО понижает trust узла (0.9->0.8 в тестах).
- ✅ GitS Network Layer завершён: автономные сервисные агенты (Tachikoma) на узлах исполняют задачи
  друг друга (goal -> remote node -> local execution -> real outcome), НЕ только обмен знаниями.
- ✅ K5: НОВЫЙ серверный порт IRemoteExecutionListener (НЕ дублирует client); wire-формат
  централизован (single-source-of-truth, client+server share); INetworkTransport/IRemoteOrchestrator/
  ReferenceOrchestrator переиспользованы.
- ✅ K1/K6: contracts + stdlib; kernel/services -> contracts only.
- ✅ O1: trust SOFT; server НЕ мутирует remote trust (доказано тестом: B не меняет trust в A при serve).
- ✅ I-09: детерминизм (correlation + fan-out); SyncTransport детерминирован.
- ⚠️ Non-scope (future): multi-hop routing / discovery узлов (только прямой dispatch на известные);
  LLM-backed remote исполнение; консенсус между узлами (только trust-gating IDT-01).

## Alternatives considered
- Встроить исполнение в `IRemoteOrchestrator` (client) -> ОТВЕРГНУТО: смешивало бы client/server
  (нарушение one-port-per-boundary). Отдельный `IRemoteExecutionListener` чище (ТЗ К5 gotcha).
- Фейковый responder вместо реального listener -> ОТВЕРГНУТО: не закрывал бы capstone (фейк-исход
  не доказывает реальное исполнение на удалённом узле).

## Evidence
- `tests/test_federated_execution.py`: 6 K8 тестов (two-node real execution success/failure;
  trust evolves from real outcome, failure lowers; trust-gating excludes low-trust; determinism;
  negative request-not-for-this-node ignored; O1 server no remote trust mutation).
- Smoke: A->B success (trust 0.9->1.0); A->B failure (trust 0.9->0.8, detail 'boom'); low-trust
  B excluded; federated node integration (client+server shared substrate).
- Full suite GREEN, gate 14/14, akb-lint PASSED.
