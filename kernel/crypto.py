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

from typing import Dict, Optional

import hashlib
import hmac

from contracts.i_signature import ISignatureProvider, extract_origin, extract_seq


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


class ReplayGuard:
    """Per-origin monotonic seq window built on CausalMark lamport (ТЗ-CRYPTO-HARDEN-01).

    `observe(envelope)` returns True iff the envelope is ACCEPTED (not a replay): its seq is
    STRICTLY GREATER than the highest seq previously seen for its origin. A seq <= last-seen is
    rejected (replay or stale duplicate). Origin = node_id/origin/author_id; seq = causal.lamport
    (reused from the existing wire format — K5 no-dup). Stateless envelopes (no seq) are always
    accepted (the guard cannot replay-protect what carries no seq; it degrades to no-op, never
    silently rejects legitimate traffic).

    The guard is SHARED between the FED-ORCH client and FED-EXEC server on a node so that a replay
    is caught at whichever handler first sees it. It is pure state (dict); it does NOT touch HARD/FSM.
    """

    def __init__(self) -> None:
        self._last: Dict[str, int] = {}

    def observe(self, envelope: dict) -> bool:
        origin = extract_origin(envelope)
        seq = extract_seq(envelope)
        if origin is None or seq is None:
            return True  # no replay key available -> cannot protect; accept (legacy-safe)
        last = self._last.get(origin)
        if last is not None and seq <= last:
            return False  # replay or stale duplicate -> reject
        # Accept and advance the window (strictly increasing per origin).
        if last is None or seq > last:
            self._last[origin] = seq
        return True

    def seen(self, origin: str) -> Optional[int]:
        return self._last.get(origin)


def build_hmac_signer(key, algorithm: str = "sha256") -> HmacSigner:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return HmacSigner(key, algorithm=algorithm)
