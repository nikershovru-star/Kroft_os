---
id: RFC-014
title: "Distributed Runtime — CRDT Knowledge Graph + Raft-lite Supervisor + Distributed EventBus (TZ-DISTRIBUTED-001)"
status: under_review
date: "2026-08-02"
related: [TZ-DISTRIBUTED-001, ADR-043, ADR-042, ADR-041, ADR-038, TZ-AGENT-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-014: Distributed Runtime

## 0. Research synthesis (2026-08-02) — см. ADR-043 §2
CRDT для collaborative KG state; Raft-lite только для leader election; distributed
EventBus поверх существующего IEventBus; sharding по tenant/type.

## 1. Problem
KG (InMemoryGraphEngine) и EventBus (InMemoryEventBus) — in-process. Нет
горизонтального масштабирования, нет tolerance к network partition, single point
of failure у Supervisor. Агенты на разных узлах не могут шарить граф/события.

## 2. Proposal

### 2.1 `ICrdtGraph` (`contracts/`)
```python
class ICrdtGraph(IGraphEngine):
    def merge(self, other: "ICrdtGraph") -> None: ...   # CRDT merge (idempotent)
    def export_ops(self) -> List[CrdtOp]: ...            # pending ops since last sync
    def apply_ops(self, ops: List[CrdtOp]) -> None: ...
@dataclass
class CrdtOp:
    kind: str          # "add_node" | "add_edge" | "touch"
    payload: dict
    node_id: str
    lamport: int       # logical clock for LWW
```
KG nodes = LWW-Element-Set (last-write-wins по Lamport clock + node_id tiebreak).
Edges = LWW-Element-Set. Versions = PN-Counter (increment on touch).

### 2.2 `CrdtGraphEngine` (`adapters/`) — drop-in `IGraphEngine`
- Реализует `IGraphEngine` (add_node/add_edge/nodes/edges) + `ICrdtGraph`.
- Локально: in-memory dict + Lamport clock. `merge()` идемпотентно.
- `export_ops()` / `apply_ops()` для sync между узлами.

### 2.3 `ILeaderElector` + `RaftLiteElector` (`contracts/` + `adapters/`)
- Только для выбора лидера Supervisor (НЕ для каждой записи).
- Heartbeat + term-based election. Leader координирует recovery (reuse WP-10
  CircuitBreaker/Degradation/IAgentRecovery), followers применяют CRDT-ops локально.
- `RaftLiteElector` — минимальный Raft (без log replication, только election).

### 2.4 `IDistributedEventBus` (`contracts/`)
```python
class IDistributedEventBus(IEventBus):
    def join(self, seed_nodes: List[str]) -> None: ...
    def leave(self) -> None: ...
```
- `GrpcEventBus` / `WebSocketEventBus` (`adapters/`) — drop-in `IEventBus`.
  Publish локально (InMemoryEventBus семантика) + replicate на peers.
  Partition → local-only publish; при reconnect — replay missed ops (CRDT).

### 2.5 Sharding (`services/`)
- По tenant (reuse `TenantIsolator`, TZ-KNOW-001) + entity-type.
- `CrossGraphRouter` — маршрутизирует query к нужному shard; on-demand cache.

### 2.6 Integration
| Компонент | Роль |
|-----------|------|
| `IGraphEngine` (Stage 26) | заменяется на `CrdtGraphEngine` (drop-in) |
| `IEventBus` (Stage 9) | заменяется на `GrpcEventBus` (drop-in) |
| SupervisorService (WP-10) | leader = `RaftLiteElector` winner |
| TenantIsolator (TZ-KNOW-001) | shard key |
| Arch Intelligence (WP-12) | мониторит partition/drift метрики |

### 2.7 API (future)
`GET /api/cluster/status` (leader, peers, partition state).

## 3. LAW Compliance
- **K1**: `ICrdtGraph`, `ILeaderElector`, `IDistributedEventBus` в contracts.
- **K3**: engines/buses/electors wire в composition.
- **K5**: leader только координирует recovery (reuse WP-10), НЕ execute.
- **K6**: узлы через IEventBus/ICrdtGraph порты.
- **K8**: distributed adapters в adapters/, НЕ в kernel/runtime.

## 4. Risks
- CRDT merge edge cases (concurrent edge to deleted node) — LWW + tombstone.
- Raft-lite split-brain при partition — term + majority; minority sleeps.
- Network transport deps (gRPC/websocket) — optional adapter, lazy import (K8).
- Latency: cross-node sync — async, eventual consistency.

## 5. Validation (при K5 go)
- CRDT: concurrent add same node (LWW), concurrent add diff nodes (both kept),
  merge idempotent (double merge = single)
- Raft-lite: 3-node election, leader fail → new election
- Distributed EventBus: pub A → sub B receives
- Partition simulate: split → local ops → merge → consistent
- Suite target: +15 tests, gate 14, akb-lint PASSED

## 6. Alternatives
- Full Raft (log replication per op) — отвергнуто (overkill для KG, slow)
- Blockchain-anchored KG — отложено (external dep, не для v1)
- Centralized DB (Postgres) — отвергнуто (SPOF, не hexagonal-local-first)
