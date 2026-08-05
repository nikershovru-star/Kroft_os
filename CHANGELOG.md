# CHANGELOG

All notable changes to KROFT_OS are documented here, grouped by ТЗ (Technical Specification).
Format: each ТЗ is one section; commits are atomic (see `git log`).

## ТЗ-NET-ROUTE-01 — node discovery + multi-hop routing (ADR-086, 2026-08-05) — DONE
- **K5:** `INodeDiscovery`+`GossipNodeDiscovery`, `IClusterRegistry`+`CrdtClusterRegistry`, `INetworkTransport` УЖЕ есть (TZ-015/ADR-044) → reuse. Новый порт `IRoutingTable` (next_hop) создан (не существовал).
- **contract** (`contracts/i_distributed_runtime.py`, `contracts/i_federated_orchestrator.py`): `IRoutingTable` + `RoutingHeader(target,ttl)`; `RemoteGoalRequest`/`RemoteOutcomeResponse` + `route`; encode/decode несут route.
- **impl** (`services/distributed_runtime.py`, `kernel/federated_orchestrator.py`, `kernel/federated_executor.py`): `ReferenceRoutingTable` (distance-vector-lite, deterministic, НЕ ре-сигнует forwarded envelope); `_maybe_forward` (форвард не-локального envelope с сохранённой подписью, per-node seen-set + progress-only next_hop = loop-safety); сервер ставит `route.target=req.author_id` (response маршрут НАЗАД).
- **integration**: `routing_table`/`direct_peers` в `build_remote_orchestrator` + `build_federated_node`.
- **tests** (`tests/test_net_routing.py`, 5 K8): discovery membership; A→C via B multi-hop; trust-gating; tampered/replayed/unsigned rejected; next_hop deterministic.
- **docs**: ADR-086 + AKB (85→86) + CHANGELOG + PROJECT_STATUS.
- **Constraints**: K1/K5/K6/K8/O1/I-09; Флаг C/1b. verify-before-trust + replay-guard на каждом hop сохранены.

## ТЗ-CAPSTONE-01 — end-to-end self-evolving federated cognitive OS (ADR-085, 2026-08-05) — DONE

The integration culmination of the vision: two authenticated, self-evolving federated nodes where node A's
self-evolution (experience → reflection → soft policy) is shipped to node B over a verified + replay-guarded
channel, and B changes its behavior from A's knowledge. No new ports/layers — reuses the entire existing
substrate (K5).

- **`composition/capstone.py`** (Флаг C, standalone, NOT in build_kernel):
  - `build_capstone_mesh(transport_a, transport_b, *, shared_key, use_real_llm, ...)` → `CapstoneMesh`:
    two `build_kernel` nodes, each wired to a `FederationSoftMemorySync` (FSE-01) over the supplied
    transports, sharing ONE `HmacSigner` (shared key) + per-node `ReplayGuard`. Real LLM is best-effort
    optional (detected via `detect_local_ollama`, else LLM-free → deterministic).
  - `run_capstone_self_evolution(mesh, ...)`: drives node A's self-evolution loop (forced failures on
    `choose_red` → `avoid:decided:choose_red` soft policy), ships the SOFT layer to B (signed + per-item
    monotonic seq), B verifies before merge and switches its next decision to the safe alternative. Returns
    a result dict for assertions.
- **Deterministic without LLM** (I-09): reference planner/executor are deterministic; the avoid policy is a
  pure function of observed failures. Real LLM only augments the advisor.
- **4 K8 tests** (`tests/test_capstone_self_evolution.py`, in-process loopback transport, no sockets):
  end-to-end loop closes locally AND propagates to B; tampered/replayed/unsigned exchange rejected;
  replayed soft layer not merged into B; deterministic without LLM.

### Constraints honored
K1/K5/K6 (composition.* → everything; reuses build_kernel, FederationSoftMemorySync, HmacSigner,
ReplayGuard, build_llm_client; no new ports), K8 (verify-before-trust + replay-guard preserved at the
FSE-01 boundary), O1 (self-evolution SOFT; HARD/FSM untouched), I-09 (deterministic without LLM), Флаг C
(standalone factories).

### Non-scope (post-MVP, documented in ADR-085)
Asymmetric crypto (Ed25519/ECDSA/RSA), key rotation/PKI, multi-hop routing/discovery/consensus, multimodal.

---

## ТЗ-CRYPTO-HARDEN-01 — hardening the crypto layer (ADR-084, 2026-08-05) — DONE

Closes the serious MVP gaps flagged by the external audit of ТЗ-CRYPTO-01 (ADR-082).

- **replay-protection** (most serious gap): `ReplayGuard` — per-origin monotonic seq window built on
  the `CausalMark.lamport` clock already carried in FED-01 + FSE-01 wire envelopes. A message with
  `seq <= last-seen` for its origin is rejected (replay / stale duplicate). A captured valid signed
  outcome can no longer be replayed to manipulate trust.
- **canonical_version**: int encoded into the envelope body; `verify_envelope` rejects a version mismatch
  (future format-skew defense). Excluded from canonical bytes so verification stays reproducible.
- **max payload size**: `MAX_ENVELOPE_BYTES` (256 KiB). `canonical_bytes` enforces the limit BEFORE
  sign/verify — oversized messages are rejected without spending CPU on HMAC.
- **unicode NFC**: `canonical_bytes` normalizes every str value via `unicodedata.normalize("NFC", s)`
  (recursive) so equivalent Unicode forms (composed/decomposed, Kelvin sign vs K) produce identical
  canonical bytes — closing a signature-forgery-via-equivalent-string vector.
- **ISigner / IVerifier split**: `ISignatureProvider` now inherits `ISigner` + `IVerifier`; a sign-only
  or verify-only object works at the boundary (minimal audit surface). `HmacSigner` implements both.

### Constraints honored
K1/K6 (stdlib hmac/hashlib/unicodedata; no external SDK in domain), K5 (no duplicated ports; reuses
`CausalMark.lamport` as replay key), K8 (reject replay/oversized/version-mismatch/unsigned/tampered),
O1 (sign/verify/replay never mutate HARD/FSM; trust SOFT via `record_outcome` only from verified +
non-replayed outcomes), I-09 (NFC + sort_keys determinism; correlation by request_id), Флаг C (standalone
factories, not in `build_kernel`).

### Backward-compat
`signature_provider=None` / `replay_guard=None` ⇒ legacy behavior preserved (32 existing CRYPTO-01 +
FED/FSE-01 tests still pass without a provider).

### Non-scope (post-MVP, documented in ADR-084)
Asymmetric crypto (Ed25519/ECDSA/RSA), key rotation/PKI, envelope Header/Payload split, cross-lang float
serialization, multi-hop routing / discovery / consensus.

### Verification
- `tests/test_crypto_harden.py`: 12 K8 passed.
- Existing CRYPTO-01 + FED/FSE-01: 32 passed (backward-compat).
- Full suite 0 failed; arch-gate 14 passed; akb-lint PASSED.

---

## ТЗ-CRYPTO-01 — authenticated origin for cross-node exchange (ADR-082, 2026-08-05) — DONE

Established the crypto substrate: `ISignatureProvider` (new port) + `HmacSigner` (stdlib HMAC-SHA256,
pre-shared per-node key). Sign outgoing facts/outcomes; verify origin + integrity BEFORE merge/trust.
Trust evolves ONLY from verified outcomes. See ADR-082 for detail. Superseded in hardening by ADR-084.
