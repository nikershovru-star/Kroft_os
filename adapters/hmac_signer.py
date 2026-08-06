"""HmacSigner adapter — ISignatureProvider over stdlib hmac/hashlib (ТЗ-MARKETPLACE-01, ТЗ-CRYPTO-01).

K5: a SEPARATE adapter-layer impl of ISignatureProvider for services/composition (which must not
import kernel/crypto.py — K6 axis rule). The kernel module keeps its own HmacSigner for kernel
code; this one lives in adapters so the marketplace (services) can sign/verify without crossing
into kernel. Same port, different layer — NOT a duplicate of the contract.

K1: stdlib only (hmac, hashlib). Deterministic (I-09): same key + payload -> same MAC.
"""

from __future__ import annotations

import hashlib
import hmac

from contracts.i_signature import ISignatureProvider


class HmacSigner(ISignatureProvider):
    """HMAC-SHA256 signer with a pre-shared symmetric key (ТЗ-CRYPTO-01). Implements ISigner+IVerifier."""

    def __init__(self, key: bytes, algorithm: str = "sha256", encoding: str = "utf-8") -> None:
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
