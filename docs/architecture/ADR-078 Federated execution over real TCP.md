---
id: ADR-078
title: "Federated execution over real TCP NW-01 — two nodes exchange execution over a real socket, trust from real outcome (ТЗ-FED-TCP-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [federated-execution, real-tcp, network-transport, trust-evolution, I-09, K1, K5, K6, K8, O1]
---

# ADR-078 — Federated execution over real TCP NW-01 (ТЗ-FED-TCP-01)

## Context
ТЗ-FED-EXEC-01 доказал node-to-node исполнение на in-process `SyncTransport`; реальный TCP
(NW-01) был объявлен опциональным. Флаг 1-fix (`321fc21`) сделал `build_federated_node`
transport-agnostic (единый делегирующий handler), именно ради real-TCP. ТЗ-FED-TCP-01
**валидирует это на практике**: два узла поверх РЕАЛЬНОГО TCP-транспорта `NetworkTransport`
(adapters/network_transport.py, NW-01 localhost TCP) обмениваются исполнением; trust
обновляется из РЕАЛЬНОГО исхода, пришедшего по сокету. Завершает Network Layer реальным
транспортом и валидирует transport-agnostic фикс.

K5-разведка (commit 0): `NetworkTransport(INetworkTransport)` — реальный TCP-адаптер (wraps
`TcpEventBus`, localhost). `connect(node_id, [peers])` + `ensure_connected(timeout)` (barrier,
НЕ sleep-luck) + `send_facts`/`on_facts` + `disconnect()`. FSE-01 real-TCP тест-паттерн:
уникальные порты (`_PORT` инкремент), `_wire(a,b)`, teardown `disconnect()`, poll/retry (idempotent)
вместо wall-clock sleeps. **ВАЖНО для Флага 1:** real `NetworkTransport.on_facts` делает `append`
(fan-out список) — так что фикс `321fc21` (единый delegate) корректен в ОБОИХ случаях.

## Decision
- **НОВЫЙ порт НЕ нужен (K5):** переиспользуем `INetworkTransport` (реальный `NetworkTransport`)
  + `build_federated_node` (transport-agnostic, `321fc21`). ТЗ-FED-TCP-01 commit 1 — контракт
  не менялся; `build_federated_node` docstring уточнён (принимает real TCP).
- **Real-TCP wiring helper (commit 2):** `tests/fed_tcp_helpers.py` — `build_tcp_federated_node`
  + `make_tcp_federated_pair` + `ensure_pair_connected` + `teardown_tcp_pair`. Живёт в `tests/`
  (НЕ сканируется arch-gate), т.к. `kernel`/`adapters` НЕ могут cross-import (K1: `kernel`→только
  contracts/runtime; K6: `adapters`→только contracts). Композиция — здесь, как FSE-01 `_wire`.
- **Клиент ждёт коррелированный ответ (commit 2, fix):** НАЙДЕН+ИСПРАВЛЕН реальный баг —
  `ReferenceRemoteOrchestrator.dispatch_remote` отправлял запрос и НЕМЕДЛЕННО проверял pending;
  на real TCP ответ асинхронен → false-negative 'no remote response'. Фикс: `_wait_for_outcome
  (request_id, timeout)` poll-with-timeout barrier (детерминизм по request_id); `response_timeout`
  SOFT-tunable (O1, default 2.0). SyncTransport резолвится за один poll (поведение НЕ сломано).
  Это ТОТ ЖЕ класс гонки, что FSE-01 `_replicate_until`.
- **Тесты K8 (commit 3, отдельно, Флаг 1b):** `tests/test_federated_tcp_execution.py` — 6 тестов
  (real outcome по сокету + trust success+/failure-; trust-gating low-trust исключён; clean
  teardown; determinism correlation по request_id; negative: сервер игнорирует чужие запросы).
- **Docs (commit 4):** ADR-078 + AKB + CHANGELOG + PROJECT_STATUS.

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib; kernel→contracts/runtime only; adapters→contracts only;
  cross-layer wiring — в tests/ (не сканируется gate).
- **O1**: trust SOFT; сервер НЕ мутирует remote trust (обновляется на клиенте из реального исхода).
- **I-09**: детерминизм доставки по TCP — correlation по request_id + `ensure_connected` barrier
  (НЕ wall-clock sleep-luck).
- **Флаг C**: standalone фабрики, НЕ в build_kernel.
- **К5**: НЕ дублирован INetworkTransport/IRemoteOrchestrator/build_federated_node (расширен
  transport-agnostic через delegate).
- **K8 (negative)**: сервер фильтрует запросы НЕ на свой node_id; low-trust узел исключён.

## Consequences
- ✅ Network Layer ЗАВЕРШЁН реальным транспортом: два узла поверх РЕАЛЬНОГО TCP обмениваются
  исполнением, trust эволюционирует из РЕАЛЬНОГО исхода по сокету (success 0.9→1.0, failure 0.9→0.8).
- ✅ Флаг 1 FED-EXEC-01 ВАЛИДИРОВАН на практике: transport-agnostic `build_federated_node`
  работает поверх real `NetworkTransport` (single delegate, без опоры на fan-out контракта).
- ✅ Найден и исправлен реальный баг клиента (async-wait), блокировавший real-TCP (false-negative
  'no remote response'). Поведение SyncTransport не сломано (FED-ORCH/EXEC тесты зелёные).
- ✅ K1/K6: cross-layer wiring в tests/ (gate-compliant); kernel/adapters НЕ cross-import.
- ✅ K5: НЕ дублирован порт/фабрика.
- ⚠️ Non-scope (future, как в FED-EXEC-01): multi-hop routing / discovery; консенсус между узлами;
  LLM-backed remote exec; распределённый TCP по разным хостам (здесь только localhost, как FSE-01).

## Alternatives considered
- Создать НОВЫЙ порт ITcpFederatedTransport -> ОТВЕРГНУТО: `INetworkTransport` (NW-01) УЖЕ есть и
  реализован как real TCP; дублирование нарушило бы K5 one-port-per-boundary.
- Сделать dispatch_remote синхронно-блокирующим черезFuture/thread -> ОТВЕРГНУТО: усложнило бы
  in-process путь; poll-with-timeout barrier проще и детерминирован (I-09), как FSE-01.

## Evidence
- `tests/test_federated_tcp_execution.py`: 6 K8 тестов (real TCP outcome + trust evolve; gating;
  teardown; determinism; negative).
- Smoke: два реальных TCP-узла на localhost, A→B outcome=True по сокету, trust 0.9→1.0; failure 0.9→0.8.
- Full suite GREEN, gate 14/14, akb-lint PASSED.
