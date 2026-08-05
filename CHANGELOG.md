# CHANGELOG

All notable changes to KROFT_OS are documented here, grouped by ТЗ (Technical Specification).
Format: each ТЗ is one section; commits are atomic (see `git log`).

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
