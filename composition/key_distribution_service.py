"""Key distribution reference impl — bootstrap-signed key records + rotation + revocation
(ТЗ-KEYDIST-01, ADR-098, Флаг C).

Standalone wiring (composition root may import adapters; gate rule: composition -> everything).
The bootstrap anchor is a PRE-SHARED HMAC key (MVP assumption, documented non-scope for real PKI).
It signs each KeyRecord; a node verifies the bootstrap signature before trusting a distributed key.

K5: reuses canonical_bytes/check_signature (i_signature) + HmacSigner (adapters). Does NOT duplicate
ISignatureProvider / IAuthorKeyRegistry. get_signer() returns an HmacSigner(key) for valid records,
None for unknown/revoked/tampered (so SkillRepository can fall back to the shared signer).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional, Set

from adapters.hmac_signer import HmacSigner
from contracts.i_key_distribution import IKeyDistribution, KeyRecord, key_envelope
from contracts.i_signature import ISignatureProvider, canonical_bytes, check_signature


class KeyDistributionService(IKeyDistribution):
    """Bootstrap-anchored key distribution with rotation + revocation (ТЗ-KEYDIST-01, Флаг C)."""

    def __init__(self, bootstrap_key: bytes, bootstrap_id: str = "bootstrap") -> None:
        self._bootstrap_key = bootstrap_key
        self._bootstrap_id = bootstrap_id
        self._records: Dict[str, KeyRecord] = {}   # author -> latest VALID record
        self._revoked: Set[str] = set()

    def _bootstrap_signer(self) -> ISignatureProvider:
        return HmacSigner(self._bootstrap_key)

    def publish_key(self, author: str, key: bytes, version: int = 1) -> "KeyRecord":
        # Rotation: a higher version supersedes; a non-increasing version is rejected.
        existing = self._records.get(author)
        if existing is not None and version <= existing.version:
            raise ValueError(
                f"key rotation requires version > {existing.version} (got {version}) for {author}"
            )
        if version < 1:
            raise ValueError("key version must be >= 1")
        # Build unsigned record, sign its canonical body with the bootstrap anchor, then attach.
        rec = KeyRecord(
            author=author, key=key, version=version,
            signed_by=self._bootstrap_id, signature="", revoked=False,
        )
        sig = self._bootstrap_signer().sign(canonical_bytes(key_envelope(rec)))
        rec = replace(rec, signature=sig)
        self._records[author] = rec
        self._revoked.discard(author)  # (re)publish re-validates a previously-revoked author
        return rec

    def fetch_key(self, author: str) -> Optional["KeyRecord"]:
        rec = self._records.get(author)
        if rec is None or rec.revoked:
            return None
        # Verify the bootstrap signature before trusting the distributed key (O1: reject tamper).
        # check_signature expects the signature INSIDE the envelope, so re-attach it for verification.
        env = {**key_envelope(rec), "signature": rec.signature}
        if not check_signature(env, self._bootstrap_signer()):
            return None
        return rec

    def is_revoked(self, author: str) -> bool:
        return author in self._revoked

    def revoke(self, author: str) -> None:
        self._revoked.add(author)
        rec = self._records.get(author)
        if rec is not None:
            self._records[author] = replace(rec, revoked=True)

    def get_signer(self, author: str) -> Optional[ISignatureProvider]:
        rec = self.fetch_key(author)
        if rec is None:
            return None
        return HmacSigner(rec.key)
