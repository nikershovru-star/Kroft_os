"""Key distribution + rotation/revocation for per-author HMAC keys (ТЗ-KEYDIST-01, ADR-098).

K1-compliant: stdlib + contracts only. K5: does NOT duplicate IAuthorKeyRegistry (AUTHOR-KEYS-01) or
ISignatureProvider (CRYPTO-01). It EXTENDS the per-author-key story with DISTRIBUTION: how a node learns
another author's key in a multi-node setting, plus rotation (version bump) and revocation. The actual
bootstrap signature uses the EXISTING canonical_bytes/attach_signature/check_signature primitives from
i_signature (reused, not re-implemented). The HMAC primitive itself stays HmacSigner (CRYPTO-01).

Why: AUTHOR-KEYS-01 bound author->key but keys were seeded in-process (build_author_key_registry).
Real multi-node nodes cannot learn each other's keys, and there is no rotation/revocation. KEYDIST-01
adds a lightweight bootstrap trust-anchor: a PRE-SHARED bootstrap key (MVP assumption) HMAC-signs
key-records; a node verifies the bootstrap signature before accepting a key. Ed25519/PKI (asymmetric,
web-of-trust, real-time OCSP-style revocation) remains post-MVP.

Read-only/non-mutating: KeyDistributionService only stores/returns KeyRecords; it never touches the
kernel/HARD/FSM (O1). Revocation marks a record, it does not delete history.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Dict, Optional

from contracts.i_signature import ISignatureProvider, canonical_bytes, check_signature
from contracts.i_author_keys import IAuthorKeyRegistry


@dataclass(frozen=True)
class KeyRecord:
    """Frozen VO: a bootstrap-signed author key record (ТЗ-KEYDIST-01).

    `key` is the author's OWN HMAC key (bytes). `signed_by` is the bootstrap anchor id that
    signed this record. `signature` is the bootstrap-anchor HMAC over the canonical body (author,
    key-hex, version, signed_by, revoked) — see key_envelope(). `revoked` marks a pulled key.
    A node MUST verify the bootstrap signature (via check_signature) before trusting `key`.
    """

    author: str
    key: bytes
    version: int
    signed_by: str
    signature: str
    revoked: bool = False

    def envelope(self) -> Dict[str, object]:
        """Canonical signing body (excludes `signature`). `key` is hex-encoded for JSON."""
        return {
            "author": self.author,
            "key": self.key.hex(),
            "version": self.version,
            "signed_by": self.signed_by,
            "revoked": self.revoked,
        }


def key_envelope(rec: "KeyRecord") -> Dict[str, object]:
    """Alias of KeyRecord.envelope for external callers (signing/verification)."""
    return rec.envelope()


class IKeyDistribution(ABC):
    """Port: multi-node key distribution with bootstrap-anchor signing + rotation + revocation.

    K5: reuses ISignatureProvider (CRYPTO-01) for the bootstrap signature and IAuthorKeyRegistry's
    intent (per-author key binding) — does NOT redefine either. get_signer() returns an
    ISignatureProvider built from the distributed key (same contract shape as IAuthorKeyRegistry).
    """

    @abstractmethod
    def publish_key(self, author: str, key: bytes, version: int = 1) -> "KeyRecord":
        """Create+sign a key-record for `author` under the bootstrap anchor. Rotation: a higher
        `version` supersedes the prior record; a non-increasing version is rejected."""
        ...

    @abstractmethod
    def fetch_key(self, author: str) -> Optional["KeyRecord"]:
        """Return the author's latest VALID key-record (bootstrap signature verified, not revoked),
        or None if unknown / revoked / tampered."""
        ...

    @abstractmethod
    def is_revoked(self, author: str) -> bool:
        """True if the author's key has been revoked."""
        ...

    @abstractmethod
    def revoke(self, author: str) -> None:
        """Mark the author's key revoked (rejects future package verification)."""
        ...

    @abstractmethod
    def get_signer(self, author: str) -> Optional[ISignatureProvider]:
        """Return an ISignatureProvider for the author's distributed key, or None if the author is
        unknown / revoked / tampered (caller falls back to shared signer for backward-compat)."""
        ...
