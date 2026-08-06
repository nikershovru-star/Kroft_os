"""SkillPackager + SkillRepository — Marketplace reference impl (ТЗ-MARKETPLACE-01, ADR-093).

K6: lives in services/ — imports ONLY contracts (i_marketplace, i_signature, i_identity, i_memory,
plugin) + adapters (hmac_signer, OK per axis rule). The ISignatureProvider + ITrustRegistry are
INJECTED (composition supplies HmacSigner / a trust registry), never imported concrete into the
signing path beyond the adapter (which is itself a port impl).

Closed loop (ТЗ-MARKETPLACE-01): package Procedure/Plugin -> sign (HMAC) -> publish -> install on
another store with signature verify + trust gate. Untrusted author or tampered payload -> rejected
(O1 safe default-deny, no mutation). New version supersedes the old (SUPERSEDED for traceability).

Determinism (I-09): HMAC + canonical_bytes give reproducible signatures; payload is asdict(...) of
the frozen source VO, so packaging is stable for identical input.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from contracts.i_identity import ITrustRegistry
from contracts.i_author_keys import IAuthorKeyRegistry
from contracts.i_memory import Procedure
from contracts.i_marketplace import ISkillRepository, SkillPackage
from contracts.i_signature import attach_signature, canonical_bytes, check_signature
from contracts.plugin import PluginManifest


def _jsonable(o: Any) -> Any:
    """Recursively convert Enums / tuples / sets to JSON-serializable forms."""
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, (tuple, list, set)):
        return [_jsonable(x) for x in o]
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    return o


class SkillPackager:
    """Package a Procedure or PluginManifest into a signed SkillPackage (ТЗ-MARKETPLACE-01)."""

    @staticmethod
    def package(obj, author: str, signer: "Any", version: int = 1) -> SkillPackage:
        if isinstance(obj, Procedure):
            payload_type = "procedure"
            capabilities = (obj.capability,)
            name = obj.name or obj.capability
        elif isinstance(obj, PluginManifest):
            payload_type = "plugin"
            capabilities = obj.capabilities
            name = obj.name
        else:
            raise TypeError(f"cannot package {type(obj).__name__}")
        payload = _jsonable(asdict(obj))
        # canonical body (no signature) -> sign -> embed
        body = {
            "id": f"{author}/{name}@v{version}",
            "name": name,
            "version": version,
            "author": author,
            "capabilities": tuple(capabilities),
            "payload_type": payload_type,
            "payload": payload,
        }
        signed = attach_signature(body, signer)
        return SkillPackage(
            id=signed["id"],
            name=signed["name"],
            version=signed["version"],
            author=signed["author"],
            capabilities=tuple(signed["capabilities"]),
            payload_type=signed["payload_type"],
            payload=signed["payload"],
            signature=signed["signature"],
        )


class SkillRepository(ISkillRepository):
    """In-memory/local-dir SkillRepository with signature verify + trust gate (ТЗ-MARKETPLACE-01)."""

    def __init__(self, signer: "Any" = None, store_dir: Optional[str] = None,
                 author_key_registry: Optional[IAuthorKeyRegistry] = None) -> None:
        # signer (ISignatureProvider) injected; store_dir optional for local-dir persistence
        self._signer = signer
        # ТЗ-AUTHOR-KEYS-01: per-author HMAC keys. When an author is registered, its OWN key
        # authenticates the package; otherwise verify falls back to the shared `signer` (backward-compat
        # with MARKETPLACE/FED-REPL/CAPSTONE shared-key usage).
        self._author_keys = author_key_registry
        self._store_dir = store_dir
        self._packages: Dict[str, SkillPackage] = {}  # id -> pkg
        self._installed: Dict[str, Any] = {}  # name -> installed payload (latest)
        self._superseded: Dict[str, List[SkillPackage]] = {}  # name -> old versions

    # --- ISkillRepository --------------------------------------------------
    def publish(self, pkg: SkillPackage) -> None:
        self._packages[pkg.id] = pkg
        if self._store_dir:
            self._persist(pkg)

    def verify(self, pkg: SkillPackage, signer: "Any" = None) -> bool:
        # ТЗ-AUTHOR-KEYS-01: prefer the author's OWN registered key; fall back to the shared signer
        # when the author is unregistered (backward-compat with shared-key MARKETPLACE/FED-REPL/CAPSTONE).
        prov = signer
        if prov is None and self._author_keys is not None and self._author_keys.has(pkg.author):
            prov = self._author_keys.get_signer(pkg.author)
        if prov is None:
            prov = self._signer
        if prov is None:
            return False
        env = {
            "id": pkg.id, "name": pkg.name, "version": pkg.version,
            "author": pkg.author, "capabilities": pkg.capabilities,
            "payload_type": pkg.payload_type, "payload": pkg.payload,
            "signature": pkg.signature,
        }
        return check_signature(env, prov)

    def install(self, pkg: SkillPackage, trust_registry: Optional[ITrustRegistry] = None,
                threshold: float = 0.5) -> Optional[Any]:
        # 1) signature integrity (tamper / wrong key -> reject, O1)
        if not self.verify(pkg):
            return None
        # 2) trust gate (untrusted author -> reject, O1 safe default-deny)
        if trust_registry is not None:
            # trust_score_of = MAX aggregate of recorded TrustMeta scores (0.0 if unknown author).
            # Unknown/untrusted authors score 0.0 -> rejected. Matches federation gating (ТЗ-IDT-01).
            score = trust_registry.trust_score_of(pkg.author)
            if score < threshold:
                return None
        # 3) decode payload -> Procedure / PluginManifest
        installed = self._decode(pkg)
        if installed is None:
            return None
        # 4) version supersede (old version SUPERSEDED for traceability)
        prev = self._installed.get(pkg.name)
        if prev is not None and getattr(prev, "version", 0) < pkg.version:
            # The previously-installed payload is demoted to SUPERSEDED. We store the decoded
            # payload (Procedure/PluginManifest) itself — it is always present regardless of whether
            # this node published the package locally (federation installs arrive without _packages).
            self._superseded.setdefault(pkg.name, []).append(prev)
        self._installed[pkg.name] = installed
        return installed

    def list(self) -> List[SkillPackage]:
        return list(self._packages.values())

    # --- helpers -----------------------------------------------------------
    def _decode(self, pkg: SkillPackage) -> Optional[Any]:
        try:
            if pkg.payload_type == "procedure":
                return Procedure(**pkg.payload)
            if pkg.payload_type == "plugin":
                return PluginManifest(**pkg.payload)
        except Exception:
            return None
        return None

    def _persist(self, pkg: SkillPackage) -> None:
        os.makedirs(self._store_dir, exist_ok=True)
        path = os.path.join(self._store_dir, f"{pkg.id.replace('/', '_')}.json")
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(asdict(pkg)), fh)

    def superseded(self, name: str) -> List[SkillPackage]:
        return list(self._superseded.get(name, []))


def build_skill_repository(signer: "Any" = None,
                           store_dir: Optional[str] = None,
                           author_key_registry: Optional[IAuthorKeyRegistry] = None) -> "SkillRepository":
    """Standalone factory (Флаг C) — wire a SkillRepository. NOT in build_kernel (opt-in)."""
    return SkillRepository(signer=signer, store_dir=store_dir,
                          author_key_registry=author_key_registry)
