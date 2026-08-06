"""Marketplace port — package / sign / publish / install skills & plugins (ТЗ-MARKETPLACE-01, ADR-093).

K1-compliant: stdlib + contracts only. K5: this is a NEW distribution seam. It does NOT duplicate:
  - contracts/i_signature.py already has ISignatureProvider + attach_signature/check_signature
    (HMAC, stdlib). We REUSE them for package signing/verification (never reimplement HMAC).
  - contracts/i_identity.py already has ITrustRegistry (trust_score_of / current_trust /
    threshold_check, ТЗ-IDT-01). We REUSE it for install trust-gating (untrusted author -> reject).
  - contracts/i_memory.py already has Procedure (frozen skill VO, with version/lifecycle from
    ТЗ-EVOLUTION-01). We REUSE Procedure as a skill payload.
  - contracts/plugin.py already has PluginManifest / ICapabilityPlugin / IPluginRegistry
    (ТЗ-PLUGIN-01). We REUSE PluginManifest as a plugin payload.
The missing piece was the packaging + distribution boundary itself -> SkillPackage + ISkillRepository.

Signature (I-09 deterministic): a package is a canonicalized dict signed with an ISignatureProvider
(HMAC, stdlib, K6). Verification re-canonicalizes and checks the MAC. Tamper or wrong key -> fail.
Trust gate (O1): install refuses packages from authors below the trust threshold; a rejected package
is NEVER applied to the local store (no mutation, safe default-deny).

Non-scope (post-MVP): Ed25519/PKI (HMAC with pre-shared author-key now); real multi-host repository
server (in-memory / local-dir now); desktop GUI (Stage 8).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from contracts.i_memory import Procedure
from contracts.plugin import PluginManifest


@dataclass(frozen=True)
class SkillPackage:
    """Signed, distributable unit of a skill or plugin (ТЗ-MARKETPLACE-01, frozen VO).

    Reuses Procedure/PluginManifest only as *source* payloads (imported, never redefined).
    `payload` is the JSON-serializable dict form (dataclasses.asdict) of a Procedure or
    PluginManifest, so the package is self-contained and deterministic to sign/verify.
    """

    id: str
    name: str
    version: int
    author: str
    capabilities: Tuple[str, ...]
    payload_type: str  # "procedure" | "plugin"
    payload: Dict[str, Any]  # asdict(Procedure | PluginManifest)
    signature: str  # HMAC MAC over canonical bytes of the body (excluding signature)


class ISkillRepository(ABC):
    """Port: publish + install signed skill/plugin packages with trust gating (ТЗ-MARKETPLACE-01).

    Contract:
      - publish(pkg): add a signed package to the repository (local store / dir).
      - verify(pkg, signer): re-canonicalize and check_signature; True iff intact + authentic.
      - install(pkg, trust_registry, threshold): verify signature AND gate on author trust
        (trust_registry.trust_score_of(author) >= threshold, or current_trust). On success, the
        decoded payload (Procedure/PluginManifest) is returned and the previous version (if any) is
        marked SUPERSEDED (traceability). On ANY failure (bad signature / untrusted author / tamper)
        returns None and applies NOTHING (O1 safe default-deny). Deterministic (I-09).
      - list(): all published packages.
    """

    @abstractmethod
    def publish(self, pkg: SkillPackage) -> None:
        raise NotImplementedError

    @abstractmethod
    def verify(self, pkg: SkillPackage, signer: "Any") -> bool:
        raise NotImplementedError

    @abstractmethod
    def install(self, pkg: SkillPackage, trust_registry=None,
                threshold: float = 0.5) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[SkillPackage]:
        raise NotImplementedError
