---
id: ADR-051
title: "Federated Knowledge Network — selective sharing, trust, identity (TZ-022)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.82
confidence: high
risk: high
related: [TZ-022, TZ-015, WP-14, ADR-047, ADR-050, Wave-3]
---

# ADR-051: Federated Knowledge Network (TZ-022)

## 1. Context
Уровень интернета знаний. Каждый пользователь хранит знания ЛОКАЛЬНО, делится только
разрешёнными частями графа (безопаснее полной синхронизации). TZ-022 добавляет:
Federation Protocol, Identity, Permissions, Trust Model, Selective Knowledge Sharing,
Synchronization, Remote Search, Cross-node Reasoning.

## 2. Research Synthesis (2026-08-02)
- **Federated Knowledge Graph** (Actian 2026): each node owns local KG, shares
  SELECTIVELY — exactly our model (safer than full sync).
- **Trust Model** (Springer 2026 Fed Survey): graph-theoretic trust (GNN learned
  scores, TidalTrust propagation), weighted voting by trust.
- **Identity/Zero-Trust** (CISA 2026): identity = new perimeter; continuous verify;
  least privilege; decentralized identity (user lockbox).
- **Selective Sharing** (TwinGuard-Sec Nature 2026): hierarchical trust → selective
  sharing by domain + policy.
- **Cross-node Reasoning** (Federated Multi-Agent): KG + LLM co-learning без raw
  data sharing; remote search.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse TcpEventBus + CrdtGraphEngine
(TZ-015/WP-14) + IIdentity (crypto) + ILlm (TZ-AGENT-001):
- `IFederationProtocol` — handshake/sync over TcpEventBus (reuse TZ-015 transport).
- `IIdentity` — decentralized node/user identity (keypair, zero-trust).
- `IPermissions` — least-privilege access control (share grants per node).
- `ITrustModel` — graph-theoretic trust scores (propagation), weighted consensus.
- `ISelectiveSharing` — export/import only permitted KG subgraphs (per-node policy).
- `ISynchronization` — CRDT KG sync across federated nodes (reuse CrdtGraphEngine).
- `IRemoteSearch` — query remote node KG без full sync (federated query).
- `ICrossNodeReasoning` — aggregate reasoning across nodes (LLM + KG merge).
- `FederationService` — orchestrates selective share + sync + trust + remote search.

## 4. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: selective sharing default DENY (only explicit grants sync); no silent full sync.
- **K6**: через IEventBus/ICrdtGraph/ILlm порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Node A (local KG) ──selective share──▶ Node B (local KG)
   │ (IIdentity + IPermissions + ITrustModel)
   └─ ISynchronization (CRDT) + IRemoteSearch + ICrossNodeReasoning
```

## 6. Validation (когда K5 go)
- identity issue/verify; permissions deny by default; trust score propagates;
  selective subgraph export/import; CRDT sync; remote search returns; cross-node
  reasoning aggregates. No full-sync without grant.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-022 (TZ-022); Actian Federated KG 2026, Springer Fed Trust 2026, CISA Zero-
  Trust 2026, TwinGuard-Sec Nature 2026, Federated Multi-Agent Reasoning
- TZ-015 (TcpEventBus), WP-14 (CrdtGraphEngine), TZ-AGENT-001 (ILlm)
