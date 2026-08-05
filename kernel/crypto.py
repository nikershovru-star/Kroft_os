"""Reference signature provider (ТЗ-CRYPTO-01, ADR-082) — HMAC over stdlib, no external SDK (K6).

HmacSigner implements `ISignatureProvider` (contracts/i_signature.py) using a PRE-SHARED per-node
key (symmetric). It authenticates both ORIGIN and INTEGRITY of a cross-node message: the receiver
verifies the sender's MAC before merging/trusting the payload, so a tampered or forged message is
rejected (verify-before-trust).

K1/K6: stdlib `hmac` + `hashlib` ONLY — no third-party crypto SDK in the domain (K6: domain layer
imports ports + stdlib, never vendor SDKs). K8: deterministic — same key + payload => same mac
(constant-time compare via hmac.compare_digest). O1: signing/verifying does NOT mutate HARD/FSM;
trust is SOFT and updated only from verified outcomes.

FUTURE (non-scope): asymmetric crypto (ECDSA/RSA) needs an external lib; key rotation/PKI/key
distribution are out of scope (reference uses one pre-shared key, set by the caller).
"""

from __future__ import annotations

from typing import Optional

import hashlib
import hmac

from contracts.i_signature import ISignatureProvider


class HmacSigner(ISignatureProvider):
    """HMAC-SHA256 signer with a pre-shared symmetric key (ТЗ-CRYPTO-01)."""

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
