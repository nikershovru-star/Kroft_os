---
id: ADR-061
title: "Real Network Federation — cognitive-kernel federation over real transport (ТЗ-NW-01)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.85
confidence: high
risk: medium
related: [ADR-054, ADR-055, ADR-056, ADR-057, ADR-058, ADR-059, ADR-060, TZ-015, CAUSAL-01, RE-01]
addresses: [TZ-NW-01, WP14-RACE, FLAG1, FLAG2]
---

## 1. Context
Когнитивные ядра (CognitiveKernel) эволюционировали как автономные узлы: каждый
замыкает свой цикл Perception → … → Decision → Execution → Observation → Reflection →
Learning → Memory Update. Но узлы НЕ делятся опытом — многопроцессорная система
(KROFT) не использует распределённый интеллект. ТЗ-NW-01 требует **реальной сети**:
федерация когнитивных ядер через настоящий TCP-транспорт, где слитый факт ВЛИЯЕТ на
Decision приёмника (cognitive value), а не просто репликация байтов.

WP14-RACE (issue WP14-RACE): leader/follower broadcast race на wall-clock timing.
ФЛАГ 1 (ТЗ-RF-01): Reflection и ME-01 оба коммитили semantic независимо — закрыт в
commit 0 (ТЗ-NW-01): ME-01 — единственный writer, дедупликация против уже закоммиченных.

## 2. Decision
- **Контракт транспорта:** `INetworkTransport` (contracts/i_network_transport.py) —
  `connect / send_event / send_facts / on_event / on_facts / ensure_connected / disconnect`.
  К6: services НЕ импортируют конкретный адаптер; `NetworkTransport` (adapters/) — это
  reference-импл поверх `TcpEventBus` (infrastructure/eventbus.py), НЕ в runtime-слое.
- **Федерация COGNITIVE:** `NetworkFederationService` (services/distributed_runtime.py)
  федерирует `CognitiveEvent` + `WorldState.facts`. На КАЖДЫЙ inbound fact идёт causal
  merge (`SharedContextService.merge_remote`, Lamport receive-bump) и merged world
  фолдится в SSOT приёмника (`InMemoryWorldState.apply_remote`) → следующий `tick`
  читает federated facts через `world.snapshot()` → Decision МЕНЯЕТСЯ.
- **Интеграция ядер:** `CognitiveKernel.attach_federation(federation)` — идемпотентный,
  проверяемый (assert receiver wired к `_on_federated_world` по `__func__`/`__self__`),
  receiver lock после bind (пост-attach override игнорируется — ФЛАГ 1 связки).
- **Детерминизация WP14-RACE:** `RaftLiteElector.wait_leader` / `CrdtGraphEngine.wait_node`
  — барьеры (`threading.Event`), просыпающиеся на событии выбора лидера, а НЕ на
  `time.sleep`. K5-поймал: `TcpEventBus.join` НЕ делает background-retry → добавлен
  `NetworkTransport.ensure_connected` (фоновый retry + барьер).

## 3. Architecture (полный путь федерации)
```
A.world.update(fact) → A.replicate_world(snapshot)
  → NetworkTransport.send_facts (wire lamport via SharedContextService.replicate_to)
  → TcpEventBus "cog.facts" (localhost TCP)
  → B.NetworkTransport._on_wire_facts
  → B.NetworkFederationService._handle_remote_facts
  → B.SharedContextService.merge_remote (Lamport receive-bump, causal dedup)
  → B._on_world_merged(merged)  [locked to B kernel SSOT fold]
  → B.CognitiveKernel._on_federated_world → B.world.apply_remote(merged)
  → B.tick(intent): world.snapshot() содержит federated fact → Decision МЕНЯЕТСЯ
```

## 4. Federation Cognitive Value — ДОКАЗАНО
Ad-hoc verifier (hermes-verify-nw01-flag1.py): **7/7 PASS**. E2E: два `build_kernel`
через `NetworkFederationService`, A реплицирует world; B получает факт в SSOT,
`base_plan('plan-0c3fa4e9') != fed_plan('plan-c54a05b7')` — Decision@B реально меняется
от federated факта. Не «replication of bytes», а влияние на deliberation.

## 5. Honest Limitations (ФЛАГ 2 — RaftLiteElector)
`RaftLiteElector` — **упрощённый Raft, НЕ production**. Экспериментально установлено:
- **(a) Нет self-election в 2-узловой паре:** одиночный узел не может выбрать себя
  лидером (нужно majority = 2 голоса), а симметричный старт двух узлов даёт
  **split-brain** (оба лидера). Асимметричный старт не помогает, пока followers не
  стартовали (leader не получает majority).
- **(c) Решение:** федеративные/кластерные тесты используют **3+ узла** (majority = 2
  достижимо без гонки) ИЛИ утверждают **«ровно один лидер»** (не конкретный узел —
  Raft fairness делает выбор узла недетерминированным по дизайну).

Эти ограничения НЕ блокируют федерацию ядер (которая поверх `TcpEventBus`, а не
Raft) — но будущие разработчики НЕ должны строить 2-узловой leader-election на
`RaftLiteElector`. Для production needs — заменить на полноценный Raft (Log replication,
Pre-Vote, membership changes) вне ТЗ-NW-01.

## 6. Known Gotchas (зафиксировано для будущих ТЗ)
- НЕ переопределять `_on_world_merged` после `attach_federation` в тестах (receiver locked).
- RaftLiteElector: 3+ узла для majority; assert «ровно один лидер», не конкретный узел.
- НЕ wall-clock sleep для синхронизации; барьеры/wait.
- TcpEventBus.join: background retry + ensure_connected барьер (двусторонняя связь
  устанавливается нестабильно без него).
- Bound methods re-create на каждом доступе → сравнивать receiver по `__func__`/`__self__`,
  НЕ `is`.
- Перед `git commit --amend` проверять `git log -1` (какой коммит последний).

## 7. Future Work
- CognitiveEvent и WorldState.facts стоит федерировать РАЗДЕЛЬНО (события → event bus,
  состояние → SharedContext), а не складывать события в facts (`_handle_remote_event`
  пишет `event:{type}:{ref_id}` в world.facts — допустимо для reference, но смешивает
  события и состояние в одном слое).
- Partition/reconnect: текущий replay-буфер в `NetworkFederationService._replay_buffer`
  буферизует facts, полученные ДО `set_local_world`; для production нужен persistent
  WAL на уровне транспорта.
