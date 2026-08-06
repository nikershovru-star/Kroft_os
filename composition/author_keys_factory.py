"""Author key registry composition (ТЗ-AUTHOR-KEYS-01, ADR-096, Флаг C).

Standalone wiring (composition root may import services + adapters, gate rule: composition ->
everything). IAuthorKeyRegistry is the contract (contracts); here we provide the concrete
AuthorKeyRegistry that resolves a per-author HMAC signer. NOT wired into build_kernel (opt-in).

The registry stores raw key bytes (data) and builds an ISignatureProvider (HmacSigner) from the
registered key on demand via get_signer(). The HmacSigner adapter lives in adapters (K6: services
cannot import it, so the registry that needs it lives here in composition, not in services).
"""

from __future__ import annotations

from typing import Dict, Optional

from adapters.hmac_signer import HmacSigner
from contracts.i_author_keys import AuthorKey, IAuthorKeyRegistry
from contracts.i_signature import ISignatureProvider


class AuthorKeyRegistry(IAuthorKeyRegistry):
    """In-memory per-author HMAC key registry (ТЗ-AUTHOR-KEYS-01, Флаг C)."""

    def __init__(self) -> None:
        self._keys: Dict[str, bytes] = {}

    def register_key(self, author: str, key: bytes) -> None:
        self._keys[author] = key

    def get_key(self, author: str) -> Optional[bytes]:
        return self._keys.get(author)

    def get_signer(self, author: str) -> Optional[ISignatureProvider]:
        key = self._keys.get(author)
        if key is None:
            return None
        return HmacSigner(key)

    def has(self, author: str) -> bool:
        return author in self._keys


def build_author_key_registry(bindings: Optional[Dict[str, bytes]] = None) -> "AuthorKeyRegistry":
    """Build a registry, optionally seeding author->key bindings (Флаг C)."""
    reg = AuthorKeyRegistry()
    if bindings:
        for author, key in bindings.items():
            reg.register_key(author, key)
    return reg
