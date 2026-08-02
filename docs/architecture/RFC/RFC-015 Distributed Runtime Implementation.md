---
id: RFC-015
title: "Distributed Runtime Implementation — 9 components (TZ-015)"
status: under_review
date: "2026-08-02"
related: [TZ-015, ADR-044, ADR-043, WP-14, TZ-AGENT-001, TZ-OBS-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-015: Distributed Runtime Implementation (TZ-015)

## 0. Research synthesis (2026-08-02) — см. ADR-044 §2
SWIM/gossip discovery; CRDT cluster registry; message-passing remote agent exec;
shared context поверх KG; OTel-style cluster metrics.

## 1. Problem
WP-14 дал ядро (CRDT KG + Raft-lite + TCP Bus + failover), но система НЕ является
полноценным кластером: нет discovery (узлы не находят друг друга динамически),
нет registry (нет единого вида кластера), нет remote agent exec (агенты не могут
исполняться на соседнем узле), нет shared context (контекст не разделён), нет
network supervisor + cluster metrics (нет Cluster-level health).

## 2. Proposal — 5 new components (4 уже в WP-14: CRDT Graph, Distributed EventBus,
Leader Election, Supervisor Failover)

### 2.1 `INodeDiscovery` (`contracts/`)
```python
class INodeDiscovery(ABC):
    def start(self, self_node: NodeInfo, seeds: List[str]) -> None: ...
    def stop(self) -> None: ...
    def known_nodes(self) -> List[NodeInfo]: ...
    def on_membership_change(self, cb: Callable[[List[NodeInfo]], None]) -> None: ...
@dataclass
class NodeInfo:
    node_id: str; addr: str; capabilities: List[str]; status: str  # alive/suspect/dead
```
`GossipDiscovery` (`adapters/`): periodически отправляет digest (known nodes) через
EventBus `cluster.gossip`; получает -> merge membership (SWIM: suspect через buddy).
Failure = нет gossip от узла N timeout -> suspect -> dead.

### 2.2 `IClusterRegistry` (`contracts/`)
```python
class IClusterRegistry(ABC):
    def register(self, node: NodeInfo) -> None: ...
    def deregister(self, node_id: str) -> None: ...
    def lookup(self, node_id: str) -> Optional[NodeInfo]: ...
    def all(self) -> List[NodeInfo]: ...
```
`CrdtClusterRegistry` (`adapters/`): node_id -> NodeInfo как CRDT-LWW-map; sync через
EventBus (reuse ICrdtGraph ops или отдельный gossip). converges across nodes.

### 2.3 `IRemoteAgentExecutor` (`contracts/`)
```python
class IRemoteAgentExecutor(ABC):
    def dispatch(self, node_id: str, agent_id: str, action: str, args: str) -> "Future[Any]": ...
    def on_remote_result(self, cb: Callable[[str, dict], None]) -> None: ...
```
`RemoteAgentExecutor` (`services/`): сериализует task -> `agent.remote.<node_id>` topic
via EventBus; node получает -> вызывает IAgentPlatform.execute() -> публикует
`agent.result.<task_id>`; initiator awaits. Reuse TZ-AGENT-001 IAgentPlatform.

### 2.4 `ISharedContext` (`contracts/`)
```python
class ISharedContext(ABC):
    def put(self, key: str, value: dict) -> None: ...
    def get(self, key: str) -> Optional[dict]: ...
    def keys(self) -> List[str]: ...
```
`SharedContextService` (`services/`): put/get -> CRDT KG (node type=CONTEXT) + telemetry
record; все узлы видят одинаковый context после merge.

### 2.5 `INetworkSupervisor` + `IClusterMetrics` (`contracts/`)
- `NetworkSupervisor` (`services/`): integrates RaftLiteElector (leader failover) +
  GossipDiscovery (node health) + WP-10 recovery (recover_cb). На leader-change ->
  пересчёт cluster health.
- `ClusterMetricsService` (`services/`): aggregates per-node metrics (via
  ITelemetrySink, TZ-OBS-001) -> publishes `cluster.health` + `cluster.metrics`.

### 2.6 Integration
| Компонент | Реализация | Где |
|-----------|-----------|-----|
| CRDT Graph | CrdtGraphEngine (WP-14) | adapters |
| Distributed EventBus | TcpEventBus (WP-14) | adapters |
| Leader Election | RaftLiteElector (WP-14) | adapters |
| Node Discovery | GossipDiscovery (NEW) | adapters |
| Cluster Registry | CrdtClusterRegistry (NEW) | adapters |
| Remote Agent Exec | RemoteAgentExecutor (NEW) | services |
| Shared Context | SharedContextService (NEW) | services |
| Network Supervisor | NetworkSupervisor (NEW) | services |
| Cluster Metrics | ClusterMetricsService (NEW) | services |

## 3. LAW Compliance
- **K1**: 6 портов в contracts.
- **K3**: wire в composition.
- **K5**: NetworkSupervisor координирует recovery (reuse WP-10), НЕ execute.
- **K6**: узлы через IEventBus/ICrdtGraph/IAgentPlatform порты.
- **K8**: adapters/services НЕ импортируют kernel/runtime.

## 4. Risks
- Gossip convergence latency (eventual).
- Remote exec serialization (agent args/results) — JSON-only.
- Network partition: CRDT + gossip graceful; minority sleeps (Raft-lite).

## 5. Validation (при K5 go)
- gossip join/leave detected; registry converges; remote agent exec returns result;
  shared context visible cross-node; supervisor failover; cluster metrics published.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Centralized registry (zookeeper-like) — отвергнуто (SPOF, не hexagonal-local).
- Full consensus per op — отвергнуто (overkill, есть CRDT).
