"""Marketplace composition (ТЗ-MARKETPLACE-01, ADR-093, Флаг C).

Standalone wiring (composition root may import services + adapters, gate rule: composition ->
everything). SkillRepository (services) imports only contracts + the hmac adapter; here we
supply the concrete HmacSigner. NOT wired into build_kernel (opt-in).
"""

from __future__ import annotations

from typing import Optional

from adapters.hmac_signer import HmacSigner
from services.skill_marketplace import SkillRepository, build_skill_repository


def build_default_marketplace(signer_key: bytes = b"kroft-shared-secret",
                              store_dir: Optional[str] = None) -> SkillRepository:
    """Build a SkillRepository over a concrete HmacSigner (Флаг C, standalone)."""
    signer = HmacSigner(signer_key)
    return build_skill_repository(signer=signer, store_dir=store_dir)
