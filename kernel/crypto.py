"""Reference signature provider (ТЗ-CRYPTO-01 ADR-082 + ТЗ-CRYPTO-HARDEN-01 ADR-084), stdlib, no external SDK (K6).

HmacSigner implements `ISignatureProvider` (= ISigner + IVerifier) over stdlib hmac/hashlib with a
pre-shared per-node key (symmetric). It authenticates both ORIGIN and INTEGRITY: the receiver
verifies the sender's MAC before merging/trusting, so a tampered/forged message is rejected
(verify-before-trust).

ReplayGuard (ТЗ-CRYPTO-HARDEN-01): per-origin monotonic seq window built on the CausalMark Lamport
clock already carried in the wire envelope (`causal["lamport"]`). A message with seq <= the last
seen seq for its origin is a REPLAY (or out-of-order duplicate) and is rejected — closing the
most serious MVP gap (an attacker could re-send a captured valid signed outcome to manipulate trust).

K1/K6: stdlib `hmac` + `hashlib` ONLY; contracts (i_signature) hold canonicalization/NFC/size rules.
K8: deterministic — same key + payload => same mac (constant-time compare via hmac.compare_digest).
Unicode NFC + size-limit live in contracts.canonical_bytes (single source of truth).
O1: signing/verifying/replay-checking does NOT mutate HARD/FSM; trust is SOFT, updated only from
verified + non-replayed outcomes.

FUTURE (non-scope, ADR-082/084): asymmetric crypto (ECDSA/RSA), key rotation/PKI, envelope
Header/Payload split, cross-lang float — out of scope.
"""

from __future__ import annotations

import hashlib
import hmac

from contracts.i_signature import ISignatureProvider, ReplayGuard  # re-export for kernel modules (K6)


class HmacSigner(ISignatureProvider):
    """HMAC-SHA256 signer with a pre-shared symmetric key (ТЗ-CRYPTO-01). Implements ISigner+IVerifier."""

    def __init__(self, key: bytes, algorithm: str = "sha256", encoding: str = "utf-8") -> None:
        # Key may be passed as str for convenience (pre-shared secret).
        if isinstance(key, str):
            key = key.encode(encoding)
        self._key = key
        self._algo = algorithm
        self._enc = encoding

    def _hashmod(self):
        algo = self._algo.lower()
        return getattr(hashlib, algo) if hasattr(hashlib, algo) else hashlib.sha256

    def sign(self, payload: bytes) -> str:
        mac = hmac.new(self._key, payload, self._hashmod())
        return mac.hexdigest()

    def verify(self, payload: bytes, mac: str) -> bool:
        if not isinstance(mac, str):
            return False
        expected = hmac.new(self._key, payload, self._hashmod()).hexdigest()
        # Constant-time compare (does not leak timing about where the mac diverges).
        return hmac.compare_digest(expected, mac)


def build_hmac_signer(key, algorithm: str = "sha256") -> HmacSigner:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return HmacSigner(key, algorithm=algorithm)
