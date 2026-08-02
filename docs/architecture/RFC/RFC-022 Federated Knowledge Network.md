---
id: RFC-022
title: "Federated Knowledge Network — selective sharing, trust, identity (TZ-022)"
status: under_review
date: "2026-08-02"
related: [TZ-022, ADR-051, TZ-015, WP-14, ADR-047, ADR-050]
authors: [kroft-architect]
evidence_level: III
---

# RFC-022: Federated Knowledge Network (TZ-022)

## 0. Research synthesis (2026-08-02) — см. ADR-051 §2
Federated KG (Actian 2026); Fed Trust graph-theoretic (Springer 2026); Zero-Trust
identity (CISA 2026); Selective Sharing (TwinGuard-Sec Nature 2026); Cross-node
Reasoning (Federated Multi-Agent).

## 1. Problem
Нет federation: знания не делятся между узлами, нет identity/permissions/trust, нет
selective sharing (только полная синхронизация — небезопасно).

## 2. Proposal — 8 components

### 2.1 `IFederationProtocol` (`contracts/`)
```python
class IFederationProtocol(ABC):
    def handshake(self, peer: str) -> bool: ...   # over TcpEventBus (reuse TZ-015)
    def announce(self, subgraph: bytes) -> None: ...
```

### 2.2 `IIdentity` (`contracts/`)
```python
class IIdentity(ABC):
    def issue(self, subject: str) -> str: ...   # keypair / DID-like
    def verify(self, subject: str, token: str) -> bool: ...
```

### 2.3 `IPermissions` (`contracts/`)
```python
class IPermissions(ABC):
    def grant(self, subject: str, scope: str) -> None: ...   # default DENY
    def allowed(self, subject: str, scope: str) -> bool: ...
```

### 2.4 `ITrustModel` (`contracts/`)
```python
class ITrustModel(ABC):
    def score(self, a: str, b: str) -> float: ...   # graph propagation
    def vote_weight(self, node: str) -> float: ...   # weighted consensus
```

### 2.5 `ISelectiveSharing` (`contracts/`)
```python
class ISelectiveSharing(ABC):
    def export_shared(self, node_id: str) -> bytes: ...   # only granted subgraph
    def import_shared(self, data: bytes, from_node: str) -> None: ...
```

### 2.6 `ISynchronization` (`contracts/`)
```python
class ISynchronization(ABC):
    def sync(self, ops: List[CrdtOp]) -> None: ...   # reuse CrdtGraphEngine
```

### 2.7 `IRemoteSearch` (`contracts/`)
```python
class IRemoteSearch(ABC):
    def query(self, peer: str, q: str) -> List[dict]: ...   # federated query
```

### 2.8 `ICrossNodeReasoning` (`contracts/`) + `FederationService` (`services/`)
Aggregate reasoning across nodes (LLM + KG merge). Reuse TcpEventBus (TZ-015) +
CrdtGraphEngine (WP-14) + ILlm (TZ-AGENT-001) + IIdentity/IPermissions/ITrustModel.

## 3. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: selective sharing default DENY; no silent full sync; identity verify before share.
- **K6**: через IEventBus/ICrdtGraph/ILlm порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Trust manipulation — bound propagation, require identity.
- Privacy leak — default DENY, explicit grants only.

## 5. Validation (при K5 go)
- identity issue/verify; permissions deny-by-default; trust propagate; selective export/
  import; CRDT sync; remote search; cross-node reasoning. No full-sync without grant.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Full sync replication — отвергнуто (privacy, your explicit requirement).
- Central server federation — отвергнуто (not local-first).
