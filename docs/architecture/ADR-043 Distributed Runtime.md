---
id: ADR-043
title: "Distributed Runtime — CRDT Knowledge Graph, Raft-lite Supervisor, Distributed EventBus (WP-14)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.82
confidence: high
risk: high
related: [TZ-DISTRIBUTED-001, ADR-042, ADR-041, ADR-038, TZ-AGENT-001, Wave-3]
---

# ADR-043: Distributed Runtime (WP-14)

## 1. Context
Wave 3: WP-12 (Arch Intelligence ✅), WP-13 (Multimodal ✅). Следующий —
распределённый runtime: агенты и KG должны работать на нескольких узлах
(horizontal scale, no single point of failure). Текущий KG (InMemoryGraphEngine)
и EventBus (InMemoryEventBus) — in-process. Conflict resolution и network
partitions не решены.

## 2. Research Synthesis (2026-08-02, world practices)
- **CRDT vs Raft** (StackOverflow, Zylos 2026): CRDT для collaborative state
  (concurrent writes выживают оба), eventual consistency, offline-merge. Raft/
  Paxos — только для leader election / linearizability / exclusive resources.
- **Distributed KG** (arxiv 2602, KnowledgeFutures): unified/reconciled entities
  across separate sources; blockchain-anchor — опционально, не для v1.
- **Multi-agent orchestration** (Azure, Confluent Kafka): event-driven pub/sub
  (partitions, consumer groups) — мы УЖЕ используем EventBus (IEventBus порт);
  расширяем до distributed pub/sub. Swarm/peer = no SPOF.
- **KG sharding** (HugeGraph, LogosKG): partition по entity-type/tenant,
  cross-graph routing, on-demand caching; poor partitioning → hotspots.

## 3. Decision
Распределённый runtime поверх существующих портов (K1/K3/K6/K8):
1. **KG = CRDT** (LWW-Element-Set для nodes/edges + PN-Counter для версий).
   `CrdtGraphEngine` реализует `IGraphEngine` (drop-in). Merge при reconnect.
2. **Supervisor = Raft-lite** — только leader election между узлами (НЕ для
   каждой записи). Leader координирует recovery (reuse WP-10 CircuitBreaker/
   Degradation). Followers локально применяют CRDT-ops.
3. **EventBus = distributed** — `GrpcEventBus` / `WebSocketEventBus` реализует
   `IEventBus` (drop-in). Publish локально + replicate; partition → local-only.
4. **Sharding** — по tenant/entity-type (reuse `TenantIsolator` из TZ-KNOW-001).
5. **Network partition** — graceful degrade: каждый узел работает локально
   (CRDT), merge при восстановлении связи. No data loss (eventual consistency).

## 4. Consequences
**Positive:** horizontal scale, no SPOF, offline-tolerant (CRDT merge).
**Negative:** eventual consistency (не linearizable KG — ок для knowledge).
**Risk:** CRDT merge complexity; Raft-lite correctness; network transport deps.

## 5. LAW Compliance
- **K1**: порты `ICrdtGraph`, `IDistributedEventBus`, `ILeaderElector` в contracts.
- **K3**: `CrdtGraphEngine`, `GrpcEventBus`, `RaftLiteElector` в composition.
- **K5**: leader только координирует recovery (reuse WP-10), НЕ execute.
- **K6**: узлы общаются через IEventBus/ICrdtGraph порты.
- **K8**: distributed adapters в adapters/, НЕ в kernel/runtime.

## 6. Validation (когда K5 go на code)
- CRDT merge test (concurrent node adds → no loss)
- Raft-lite election test (leader chosen, failover)
- Distributed EventBus test (pub on node A → sub on node B)
- Network partition simulate (split → merge → consistent)
- Arch-gate: K1/K6/K8. Suite target: +15 tests.

## 7. References
- RFC-014 (TZ-DISTRIBUTED-001)
- StackOverflow CRDT vs Raft, Zylos CRDT multi-agent 2026
- arxiv 2602 Distributed KG, Confluent event-driven agents
- TZ-AGENT-001 (agent substrate), WP-10 (recovery), ADR-042 (Arch Intelligence)
