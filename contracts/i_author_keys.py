"""Author key registry port — per-author HMAC keys (ТЗ-AUTHOR-KEYS-01, ADR-096).

K1-compliant: stdlib + contracts only. K5: this is a NEW seam binding an AUTHOR to a SPECIFIC
HMAC key. It does NOT duplicate ISignatureProvider (CRYPTO-01) — it only STORES per-author keys
and hands back an ISignatureProvider (a HmacSigner) built from the registered key. The signing
itself still uses the existing ISignatureProvider / HmacSigner (reused, not re-implemented).

Why: MARKETPLACE-01 / FED-REPL-01 / CAPSTONE-02 signed EVERY package with ONE shared HMAC key,
so a signature proved "someone with the shared key signed this" but NOT "alice signed this"
(Flag 3, accumulated across 3 TZ). Per-author keys close that gap pragmatically (stdlib HMAC,
no external crypto lib). Full Ed25519/PKI remains post-MVP.

Backward-compat: a node MAY still use a single shared key. When an author is NOT registered in
the registry, the receiver falls back to the shared signer (Флаг: legacy MARKETPLACE/FED-REPL/
CAPSTONE scenarios keep working). When registered, the author's OWN key authenticates the package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from contracts.i_signature import ISignatureProvider


@dataclass(frozen=True)
class AuthorKey:
    """Frozen VO binding an author id to its HMAC key (ТЗ-AUTHOR-KEYS-01)."""

    author: str
    key: bytes


class IAuthorKeyRegistry(ABC):
    """Port: per-author HMAC key storage + signer resolution (ТЗ-AUTHOR-KEYS-01).

    Contract:
      - register_key(author, key): bind author -> key (idempotent re-bind allowed).
      - get_key(author) -> key bytes or None (unregistered).
      - get_signer(author) -> ISignatureProvider built from the registered key, or None if the
        author is unregistered (caller falls back to the shared signer for backward-compat).
      - has(author) -> bool.
    The registry NEVER implements HMAC itself; get_signer returns an injected/constructed
    ISignatureProvider (the concrete HmacSigner lives in adapters/composition, K6-clean).
    """

    @abstractmethod
    def register_key(self, author: str, key: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_key(self, author: str) -> Optional[bytes]:
        raise NotImplementedError

    @abstractmethod
    def get_signer(self, author: str) -> Optional[ISignatureProvider]:
        raise NotImplementedError

    @abstractmethod
    def has(self, author: str) -> bool:
        raise NotImplementedError
