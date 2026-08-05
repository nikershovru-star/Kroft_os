---
id: ADR-086
title: Node discovery + multi-hop routing (ТЗ-NET-ROUTE-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-044   # NW-01 / TZ-015 network transport + discovery
  - ADR-075   # FED-ORCH-01 client
  - ADR-076   # FED-EXEC-01 server
  - ADR-082   # CRYPTO-01 authenticated origin
  - ADR-084   # CRYPTO-HARDEN-01 replay/version/size/unicode/split
  - ADR-085   # CAPSTONE-01 (end-to-end)
addresses:
  - TZ-NET-ROUTE-01
evidence_level: V
---

# ADR-086 — Node discovery + multi-hop routing (ТЗ-NET-ROUTE-01)

## Context
Федерация была point-to-point с жёстко заданными адресами. Для реальной масштабируемой
GitS-сети узлы должны (a) обнаруживать друг друга (gossip membership) и (b) маршрутизировать
dispatch/soft-layer-обмен через промежуточные узлы до не-прямого пира. Закрывает последний
блок масштабируемости Network Layer (после CRYPTO-01/HARDEN-01 auth+replay и CAPSTONE-01 E2E).

## K5 reconnaissance (commit 0)
- `INodeDiscovery` (start/members/is_alive) + `GossipNodeDiscovery` — **уже есть** (TZ-015/ADR-044).
- `IClusterRegistry` (register/lookup/all) + `CrdtClusterRegistry` — **уже есть** (services).
- `INetworkTransport` (broadcast send_facts/on_facts) — **уже есть** (NW-01 carrier).
- `ReferenceRemoteOrchestrator.dispatch_remote` (trust-gate → sign → broadcast → poll) — **есть**.
- `IRoutingTable` (next_hop) — **НЕ существовал** → создан новый порт (K5: doesn't exist ⇒ new).

Решение: НЕ дублировать discovery/registry/transport; создать ТОЛЬКО `IRoutingTable` + расширить
FED-конверты `RoutingHeader` (target+ttl). Все существующие узлы переиспользуются.

## Decision
1. **Routing port** — `IRoutingTable.update(self_id, members, direct_peers)` + `next_hop(target)`.
2. **ReferenceRoutingTable** (deterministic, LLM-free, I-09): distance-vector-lite. next_hop
   возвращает direct-peer, делающий МАКСИМАЛЬНЫЙ forward-progress к target (строго ближе self) в
   кольце sorted membership. Гарантирует loop-free прогресс в connected-графе; нет пути ⇒ None (drop).
3. **Multi-hop forwarding** — не-локальный envelope (route.target ≠ self) форвардится к next_hop
   через broadcast-carrier. КРИТИЧНО: форвардер НЕ мутирует тело (не декрементит ttl внутри
   подписанного тела) — иначе оригинальная подпись ломается и финал reject'ит легитимный envelope.
   Provenance/origin сохраняется end-to-end; verify-before-trust + replay-guard бегут ТОЛЬКО на финале.
4. **Loop-safety** — per-node `seen`-set (key = marker+request_id+ttl, отдельно для request/response)
   + progress-only next_hop. TTL — информационный (не мутируется при форварде).
5. **Response route-back** — сервер ставит route.target = req.author_id (оригинальный requester),
   response маршрутизируется НАЗАД тем же механизмом. Trust эволюционирует из verified+non-replay
   исхода удалённого узла даже через посредника.

## Consequences
- ✅ Network Layer масштабируем: point-to-point → multi-hop mesh (A → C через B).
- ✅ verify-before-trust + replay-guard сохранены на каждом hop (CRYPTO-01/HARDEN-01 не ослаблены).
- ✅ trust-gating (LATEST trust ≥ threshold) бежит на клиенте до dispatch; failure реально понижает.
- ✅ K5: НЕ создано лишних портов (1 новый IRoutingTable + envelope route-header).
- ⚠️ (post-MVP, non-scope): консенсус (BFT/RAFT), distributed TCP по разным хостам, PKI/Ed25519.

## Acceptance (proven by tests/test_net_routing.py, 5 K8 tests)
- discovery заполняет membership; dispatch к не-прямому пиру через посредника succeeds;
- trust-gating + verify/replay сохранены на каждом hop; determinism (next_hop чистая функция).
