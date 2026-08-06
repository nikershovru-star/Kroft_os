"""SkillDistributor — federation replication of signed SkillPackages (ТЗ-FED-REPL-01, ADR-094).

K6: lives in services/ — imports ONLY contracts (i_skill_distributor, i_marketplace, i_network_transport,
i_identity). The ISkillRepository (verify+install on the receiver) + INetworkTransport (ship) + optional
ITrustRegistry (trust gate) are INJECTED (composition supplies them), never imported concrete.

Closed loop (ТЗ-FED-REPL-01): node A publishes a signed SkillPackage via INetworkTransport.send_soft_layer;
node B's on_soft_layer handler rebuilds the package and calls on_remote_package -> SkillRepository.install
(verify signature + trust gate + version supersede). Follows the FederationSoftMemorySync (FSE-01) shape:
publish via send_soft_layer, receive via on_soft_layer, verify + trust-gate before applying.

Determinism (I-09): package serialization is stable; the receiver re-verifies the SAME signature. O1:
a node NEVER installs before verifying signature AND gating on author trust — untrusted/tampered -> None.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from contracts.i_identity import ITrustRegistry
from contracts.i_marketplace import ISkillRepository, SkillPackage
from contracts.i_network_transport import INetworkTransport
from contracts.i_skill_distributor import ISkillDistributor


class SkillDistributor(ISkillDistributor):
    """Reference Skill Distributor: replicate signed packages across nodes (ТЗ-FED-REPL-01)."""

    def __init__(self, self_node_id: str, repository: ISkillRepository,
                 transport: Optional[INetworkTransport] = None,
                 trust_registry: Optional[ITrustRegistry] = None,
                 trust_threshold: float = 0.5) -> None:
        self._node_id = self_node_id
        self._repo = repository          # injected ISkillRepository (verify+install on receiver)
        self._trust = trust_registry      # injected ITrustRegistry (optional gate)
        self._threshold = trust_threshold
        self._transport = transport
        if transport is not None:
            # same wiring pattern as FederationSoftMemorySync (FSE-01): subscribe once
            transport.on_soft_layer(self._handle_inbound)

    def bind(self, transport: INetworkTransport) -> None:
        """Wire this distributor to a transport's inbound soft-layer channel (Флаг C)."""
        self._transport = transport
        transport.on_soft_layer(self._handle_inbound)

    # --- ISkillDistributor --------------------------------------------------
    def publish_remote(self, pkg: SkillPackage, transport: INetworkTransport) -> None:
        """Ship a signed package to peers via INetworkTransport.send_soft_layer."""
        transport.send_soft_layer([asdict(pkg)], self._node_id)

    def on_remote_package(self, pkg_dict: Dict[str, Any],
                         trust_registry: Optional[ITrustRegistry] = None,
                         threshold: float = 0.5) -> Optional[Any]:
        """Receive one package dict: verify + trust-gate + install (O1: only if valid)."""
        try:
            pkg = SkillPackage(**self._normalize(pkg_dict))
        except Exception:
            return None
        gate = trust_registry if trust_registry is not None else self._trust
        return self._repo.install(pkg, trust_registry=gate, threshold=threshold)

    # --- transport handler (FSE-01 shape) ----------------------------------
    def _handle_inbound(self, items: List[Dict[str, Any]], sender_node_id: str) -> None:
        """on_soft_layer handler: each item is one serialized SkillPackage."""
        for item in items:
            self.on_remote_package(item, trust_registry=self._trust, threshold=self._threshold)

    @staticmethod
    def _normalize(d: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce JSON-round-tripped fields back to the frozen VO shape (tuple capabilities)."""
        d = dict(d)
        if isinstance(d.get("capabilities"), list):
            d["capabilities"] = tuple(d["capabilities"])
        return d


def build_skill_distributor(self_node_id: str, repository: ISkillRepository,
                           transport: Optional[INetworkTransport] = None,
                           trust_registry: Optional[ITrustRegistry] = None,
                           trust_threshold: float = 0.5) -> "SkillDistributor":
    """Standalone factory (Флаг C) — wire a SkillDistributor over injected ports."""
    return SkillDistributor(self_node_id=self_node_id, repository=repository,
                           transport=transport, trust_registry=trust_registry,
                           trust_threshold=trust_threshold)
