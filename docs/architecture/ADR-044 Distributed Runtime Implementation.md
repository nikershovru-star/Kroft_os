---
id: ADR-044
title: "Distributed Runtime Implementation — TZ-015 (full 9 components)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.83
confidence: high
risk: high
related: [TZ-015, ADR-043, RFC-014, WP-14, TZ-AGENT-001, TZ-OBS-001, Wave-3]
---

# ADR-044: Distributed Runtime Implementation (TZ-015)

## 1. Context
WP-14 (ADR-043) реализовал ядро: ICrdtGraph/CrdtGraphEngine (CRDT KG), ILeaderElector/
RaftLiteElector (election), IDistributedEventBus/TcpEventBus (pub/sub), SupervisorFailover.
TZ-015 требует ПОЛНУЮ распределённую систему из 9 компонентов. Осталось 5: Node
Discovery, Cluster Registry, Remote Agent Execution, Shared Context, Network
Supervisor + Cluster Metrics. Цель: один экземпляр KROFT_OS → распределённая
сеть (Node A <-> B <-> C).

## 2. Research Synthesis (2026-08-02)
- **Node Discovery**: SWIM/gossip (probabilistic membership, buddy-verification
  failure detection) — лучше heartbeat-only (HighScalability, Codelit 2025, PMC 2025).
- **Cluster Registry**: service-registry pattern (node->addr map); у нас CRDT —
  registry как CRDT-map, sync через EventBus.
- **Remote Agent Execution**: message-passing / episode-turn-message (AgentJet 2026,
  Confluent); reuse IAgentPlatform (TZ-AGENT-001) + EventBus.
- **Shared Context**: persistent memory layer поверх KG + vector (DeLM 2026, Cisco).
- **Cluster Metrics**: OpenTelemetry-подобный подход; reuse ITelemetrySink (TZ-OBS-001).

## 3. Decision (5 new components, reuse WP-14 substrate)
1. **INodeDiscovery / GossipDiscovery** (adapters) — SWIM-style gossip membership
   over TcpEventBus; detects join/leave/failure via indirect probing.
2. **IClusterRegistry / CrdtClusterRegistry** (adapters) — node_id -> (addr, caps,
   status) as CRDT-map; converges across nodes.
3. **IRemoteAgentExecutor / RemoteAgentExecutor** (services) — sends agent task
   messages to remote node via EventBus; awaits result; reuse IAgentPlatform.
4. **ISharedContext / SharedContextService** (services) — read/write shared state
   in CRDT KG + telemetry; agents on any node see same context.
5. **INetworkSupervisor / NetworkSupervisor** (services) — integrates RaftLiteElector
   (leader failover) + node health (from discovery) + recovery (reuse WP-10).
   **IClusterMetrics / ClusterMetricsService** (services) — aggregates node/cluster
   metrics via ITelemetrySink; publishes cluster.health.

## 4. LAW Compliance
- **K1**: порты INodeDiscovery, IClusterRegistry, IRemoteAgentExecutor, ISharedContext,
  INetworkSupervisor, IClusterMetrics в contracts.
- **K3**: adapters/services wire в composition.
- **K5**: NetworkSupervisor только координирует recovery (reuse WP-10), НЕ execute.
- **K6**: узлы через IEventBus/ICrdtGraph порты.
- **K8**: adapters/services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Node A <----> Node B <----> Node C
  CRDT KG (sync) | TcpEventBus (pub/sub) | Raft-lite (leader)
  GossipDiscovery | ClusterRegistry | RemoteAgentExec | SharedContext | NetSupervisor
```

## 6. Validation (когда K5 go)
- Node join/leave detected via gossip
- Cluster registry converges (all nodes see all peers)
- Remote agent task executes on neighbor, result returns
- Shared context visible across nodes (CRDT merge)
- Network supervisor failover on leader loss
- Cluster metrics published
- Suite target: +12 tests, gate 14, akb-lint PASSED

## 7. References
- RFC-015 (TZ-015); ADR-043 (WP-14); WP-14 code
- SWIM/gossip (HighScalability, Codelit, PMC 2025); AgentJet 2026; DeLM 2026; Cisco OTel
- TZ-AGENT-001 (IAgentPlatform), TZ-OBS-001 (ITelemetrySink), WP-10 (recovery)
