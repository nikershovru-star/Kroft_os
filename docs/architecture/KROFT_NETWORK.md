# KROFT LOCAL NETWORK — Multi-Node Federation + Hermes Operator

> Статус: KROFT-NET-01..04 реализованы и верифицированы (2026-08-16).
> Режим: REUSE EXISTING SUBSTRATE — НЕ создана вторая федерация/transport/trust/identity
> (K5). Все компоненты переиспользуют существующий substrate (ADR-030).

## Архитектура (целевая)

```
                    USER
                      │
                 ┌──────────┐
                 │  HERMES  │  operator (НЕ часть kernel)
                 │  BRIDGE  │
                 └────┬─────┘
           kroft.list / kroft.network.* / kroft.search(node,...)
                      │
            ┌─────────┴─────────┐
            │  KROFT LOCAL NET  │  KroftNodeManager (subprocess per node)
            └─────────┬─────────┘
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │KROFT-01 │  │KROFT-02 │  │KROFT-03 │   each = independent KroftApp
   │Research │  │ Coding  │  │Personal │   + own state_root
   └────┬────┘  └────┬────┘  └────┬────┘
        └──────── federation (existing tcp_event_bus / crdt_graph) ──────┘
```

## Принципы (ТЗ §41 последовательность)

```
EXISTING KROFT → INSTANCE ISOLATION → 2 LOCAL NODES → KNOWLEDGE EXCHANGE
             → HERMES OPERATOR → 5 NODES → 10 NODES → REMOTE KROFT
```

## Instance Identity (ТЗ §3)

Каждый узел = независимый `KroftApp` с уникальным `node_id` (задаётся оператором
через `--node_id`, НЕ hostname/localhost). Identity стабильна между рестартами
(сохраняется в `<state_root>/<node_id>/`).

Минимум полей (ТЗ §3):
- `node_id` — уникальный строковый id (например `kroft-01`)
- `instance_id` — генерируется/читается из state_root
- `public_key` — через существующий `i_signature`
- `trust_profile` — `ReferenceTrustRegistry` (per-instance, in-memory)
- `capabilities` — search/query/resolve/knowledge_exchange

## State Isolation (ТЗ §6/§30/§31) — KROFT-NET-01

Каждый узел получает изолированный `state_root`:

```
<state_root>/<node_id>/
    _snapshot.json          # graph + content index (KnowledgeSnapshotStore)
    _runtime_snapshot.json  # trust/procedural/episodes/semantic/normative
```

`KroftConfig.state_root` (run_kroft.py) переопределяет путь снапшота:
если `state_root` задан → `<state_root>/<node_id>/_snapshot.json`, и runtime-store
автоматически в той же директории (через `dirname`). Identity/Trust — in-memory
per-instance (НЕ singleton), поэтому два процесса полностью изолированы.

**Доказано тестами:** `test_kroft_net_isolation.py` — два `KroftApp` с разными
`state_root` имеют разные snapshot/runtime/registry/graph объекты.

## Port Allocation (ТЗ §7)

Не зашито в код — `KroftNodeManager` / декларативный config задаёт `node_id → port`.
Диапазон 7101..7110 (config-driven, не константа).

## Local Node Manager (ТЗ §4/§5) — KROFT-NET-02

`services/kroft_node_manager.py` — thin orchestration поверх `subprocess` запуска
существующего `run_kroft.py` с `--node_id --state-root --port`. НЕ новая федерация.

API:
- `start(spec)` / `stop(node_id)` / `restart(node_id)`
- `status(node_id)` / `list_nodes()`
- `load_config(path)` — YAML: `nodes: [{id, role, port, state_root}]`

**MVP (ТЗ §25):** 1/2/3 ноды поддерживаются; 5/10 — целевая нагрузка (не блокирует).

## KnowledgeEnvelope (ТЗ §11/§12/§13/§14/§15/§16) — KROFT-NET-03

`contracts/knowledge_envelope.py` — value object, переиспользующий СУЩЕСТВУЮЩИЕ типы:
- `origin` → `KnowledgeOrigin` (LOCAL/FEDERATED/INGESTED, ADR-028 Этап 4)
- `resolution` → `ResolutionLevel` (EVIDENCE..SYSTEM, ADR-028 Этап 1)
- `provenance` → abstraction_sidecar chain (fact → episode ids)
- `confidence` → SemanticFact.confidence
- `signature` → `i_signature.attach_signature`/`verify_envelope`
- `lamport`/`seen_by` → `ReplayGuard` routing semantics (ТЗ §18)

`accept_or_quarantine()` — trust-gate (`ITrustRegistry.current_trust` threshold) +
signature-gate + provenance-preservation. QUARANTINE при soft-fail (НЕ молча drop).

**НЕ реализовано (ждёт KROFT-NET-05/06 remote + multi-hop):** wire передача по сети
(надо поднять tcp_event_bus между нодами), CRDT-мутация при accept.

## Hermes Operator Bridge (ТЗ §8/§9/§10/§24) — KROFT-NET-04

`bridges/kroft_network_bridge.py` — расширяет `kroft_bridge.py` (H0) мульти-нодой:

```python
kroft_list()                       # Hermes видит все ноды
kroft_network_status()             # network overview (ТЗ §28)
kroft_network_start(node_id, ...)  # boot node via KroftNodeManager
kroft_network_stop(node_id)
kroft_status(node_id)              # delegate to specific node
kroft_search(node_id, query)       # ...
kroft_query / kroft_resolve / kroft_audit(node_id, target)
```

Hermes = operator, НЕ часть CognitiveKernel (ТЗ §8/§24). Bridge reuse KroftNodeManager
+ KroftBridge (READ-ONLY для индивидуальных нод).

## CLI (ТЗ §21)

Декларативный config `nodes.yaml`:
```yaml
nodes:
  - id: kroft-01
    role: research
    port: 7101
  - id: kroft-02
    role: coding
    port: 7102
```

`KroftNodeManager.load_config("nodes.yaml")` → запуск всех нод.

## Observability (ТЗ §28)

`kroft_network_status()` возвращает: nodes / online / offline / per-node details.
Расширяется в KROFT-NET-05 (knowledge exchanges, quarantine count, replay attempts).

## Verification (2026-08-16)

```
pytest tests/test_kroft_net_isolation.py tests/test_kroft_node_manager.py \
       tests/test_knowledge_envelope.py tests/test_kroft_network_bridge.py
→ 14 passed
```

Production snapshot (`KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json`, SHA 3b36699d) НЕ
изменён — все тесты используют TEMP state_root, re-embedding НЕ выполняется (ТЗ §32).

## KnowledgeEnvelope wire transfer + multi-hop (ТЗ §18/§19/§20) — KROFT-NET-05

`services/knowledge_envelope_router.py` — `KnowledgeEnvelopeRouter` оборачивает существующий
`TcpEventBus` (carrier, НЕ новый transport — K5). Подписывается на топик `kroft.knowledge`.

Send (MODE B SHARE, ТЗ §20):
- подписывает envelope через `attach_signature` (HmacSigner, i_signature)
- публикует wire-dict в `kroft.knowledge`

Receive:
1. loop-safety: drop если `self.node_id in seen_by`
2. `verify_envelope(dict, signer, ReplayGuard)` — signature + version + size + replay (i_signature)
3. если `recipient != self` и `ttl > 1` → forward (multi-hop): восстанавливает envelope,
   `ttl-1`, добавляет себя в `seen_by`, публикует (ТЗ §18 A→B→C)
4. если `recipient == self` → `accept_or_quarantine` (trust-gate) → ACCEPT: сохраняет в
   `<state_root>/received/` + callback; QUARANTINE: отклоняет (KROFT-NET-06 добавит store)

Replay key = (sender/origin, lamport). Re-sending the SAME envelope → второй rejected (ТЗ §29).

**Доказано тестами:** `tests/test_knowledge_envelope_router.py` (3) — A→B direct accept,
A→B→C multi-hop, replay rejected (real TCP, 3 nodes).

## Quarantine store + failure handling (ТЗ §16/§28/§29) — KROFT-NET-06

`KnowledgeEnvelopeRouter` больше НЕ теряет отклонённые конверты (ТЗ §16 «не должно
молча исчезать»). Реализовано:

- `quarantined()` — список `(EnvelopeStatus, KnowledgeEnvelope, reason)`.
- `set_on_quarantine(cb)` — callback при quarantine/reject.
- persist в `<state_root>/quarantine/<kid>.<STATUS>.json`.
- При `verify_envelope == False` (плохая подпись / replay) → `REJECTED` в quarantine.
- При trust-gate `QUARANTINED` → тоже в quarantine store (не drop).

Failure-тесты (`tests/test_knowledge_envelope_router.py`, 4):
- low trust (effective < threshold 0.3) → QUARANTINED
- bad/forged signature → REJECTED (в quarantine, не молча drop)
- TTL exhausted (recipient вне сети, ttl=1) → graceful no-op, без падения
- node offline (peer leave) → sender НЕ падает (graceful failure)

**Критический баг, найденный и исправленный в KROFT-NET-06:** multi-hop forward
пересериализовывал envelope через `KnowledgeEnvelope.to_wire()`, который НЕ сохраняет
`causal`/`lamport`/`signature`/`_canonical_version` → промежуточный узел пересылал
«голый» конверт → receiving node не мог верифицировать подпись. Исправлено: forward
шлёт ОРИГИНАЛЬНЫЙ `event` dict (модифицируя `ttl`/`seen_by`), плюс guard против
self-loop echo (`env.sender != self.node_id`).

## Remote node readiness (ТЗ §34) — KROFT-NET-07

Transport-слой REMOTE-READY. `TcpEventBus` (adapters/tcp_event_bus.py) уже принимает
`host` (default `127.0.0.1`); узел, слушающий на `0.0.0.0`, доступен с других машин.
`kroft_runtime_factory.build_runtime(host=..., federation=True, peers=[...])` уже
поднимает `TcpEventBus(host=config.host)` и join-ит к peers — готовый remote-путь.

Добавлено в KROFT-NET-07:
- `KroftNodeManager.NodeSpec.host` + `start()` шлёт `--host` в `run_kroft.py`.
- `run_kroft.py --host` CLI → `KroftConfig.network_host` (default `127.0.0.1`; `0.0.0.0` для remote).
- `NodeStatus.host` (observability).

Тест (`tests/test_kroft_remote_ready.py`, 2): узел A binds `0.0.0.0`, B коннектится
через явный seed `127.0.0.1:portA` → envelope доставлен (та же механика что и internet,
loopback вместо внешнего IP). Реальный cross-PC тест вне scope (нужны 2 машины +
firewall/NAT hole — ops-задача вне кода).

## Next (не done)

- 5/10 nodes load test
- Observability dashboard (exchanges/quarantine/replay counts, ТЗ §28)
