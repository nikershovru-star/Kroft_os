"""Skill Distributor composition (ТЗ-FED-REPL-01, ADR-094, Флаг C).

Standalone wiring (composition root may import services + adapters, gate rule: composition ->
everything). SkillDistributor (services) imports only contracts; here we supply the concrete
SkillRepository + INetworkTransport + ITrustRegistry. NOT wired into build_kernel (opt-in).
"""

from __future__ import annotations

from typing import Optional

from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from services.skill_marketplace import SkillRepository
from services.skill_distributor import SkillDistributor, build_skill_distributor


def build_default_skill_distributor(self_node_id: str,
                                   signer=None,
                                   transport: Optional[INetworkTransport] = None,
                                   trust_registry: Optional[ITrustRegistry] = None,
                                   trust_threshold: float = 0.5,
                                   store_dir: Optional[str] = None) -> SkillDistributor:
    """Build a SkillDistributor over a concrete SkillRepository + transport (Флаг C)."""
    repository = SkillRepository(signer=signer, store_dir=store_dir)
    return build_skill_distributor(
        self_node_id=self_node_id, repository=repository,
        transport=transport, trust_registry=trust_registry,
        trust_threshold=trust_threshold,
    )
